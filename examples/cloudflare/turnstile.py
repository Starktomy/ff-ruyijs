"""Run Cloudflare's public Turnstile integration tests with the native runtime.

python -m ruyijs.examples cloudflare
python -m ruyijs.examples cloudflare --case fail
python -m ruyijs.examples cloudflare --verification spent

Uses the official unmodified api.js and public dummy keys on a local document.
The Python host submits the returned dummy token to Siteverify. Production
sitekeys, secrets, browser profiles and challenge protocol emulation are not used.
"""

import argparse
import json
import math
from pathlib import Path
import sys
from time import monotonic
from urllib.parse import urlencode, urlsplit
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[2]
if (ROOT / "python/ruyijs/__init__.py").is_file():
    sys.path.insert(0, str(ROOT / "python"))

from ruyijs import Context, JSError

API = "https://challenges.cloudflare.com/turnstile/v0/api.js"
SITEVERIFY = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
SITEKEYS = {
    "pass": "1x00000000000000000000AA",
    "fail": "2x00000000000000000000AB",
    "invisible": "1x00000000000000000000BB",
    "fail-invisible": "2x00000000000000000000BB",
}
SECRETS = {
    "pass": "1x0000000000000000000000000000000AA",
    "reject": "2x0000000000000000000000000000000AA",
    "spent": "3x0000000000000000000000000000000AA",
}
PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>Turnstile official integration test</title>
<script>
window.turnstileTest = {token:null, errorCode:null, pageErrors:[]};
function onTestSuccess(token) { turnstileTest.token = token; }
function onTestFailure(code) { turnstileTest.errorCode = String(code); return true; }
addEventListener('error', function(event) {
  if (turnstileTest.pageErrors.length < 20)
    turnstileTest.pageErrors.push(String(event.message || 'Resource load failed').slice(0, 500));
});
</script>
<script src="__API__" async defer></script></head><body>
<form><div class="cf-turnstile" data-sitekey="__SITEKEY__"
data-callback="onTestSuccess" data-error-callback="onTestFailure"
data-retry="never"></div></form></body></html>"""
STATE = """({
  token: turnstileTest.token, errorCode: turnstileTest.errorCode,
  pageErrors: turnstileTest.pageErrors, apiLoaded: typeof turnstile === 'object',
  documentIframeCount: document.querySelectorAll('iframe').length,
  responseValue: (document.querySelector('[name="cf-turnstile-response"]') || {}).value || null
})"""


def record_error(report, error):
    if len(report["scriptErrors"]) < 20:
        report["scriptErrors"].append({"name": error.name, "message": error.message[:500]})


def verify(token, mode, proxy, timeout):
    # This is the server-side step: the public dummy secret stays in Python.
    proxies = {"http": proxy, "https": proxy} if proxy else {}
    opener = build_opener(ProxyHandler(proxies))
    request = Request(SITEVERIFY, data=urlencode({
        "secret": SECRETS[mode], "response": token,
    }).encode("ascii"), headers={"Content-Type": "application/x-www-form-urlencoded"})
    with opener.open(request, timeout=timeout) as response:
        body = response.read(65537)
    if len(body) > 65536:
        raise ValueError("Siteverify response exceeds 64 KiB")
    result = json.loads(body)
    if not isinstance(result, dict) or type(result.get("success")) is not bool:
        raise ValueError("Siteverify returned an unexpected response")
    return result


def run(args, report):
    deadline = monotonic() + args.timeout
    expected_widget = "failed" if args.case.startswith("fail") else "passed"
    report["expected"] = {"widget": expected_widget, "verification": args.verification}
    with Context(proxy=args.proxy, timeout=args.timeout) as context:
        report["transport"] = context.transport
        context.configure_clock("system")
        html = PAGE.replace("__API__", API).replace("__SITEKEY__", SITEKEYS[args.case])
        state = None
        try:
            context.load_page("http://localhost/turnstile-test", html)
            while monotonic() < deadline:
                state = context.eval(STATE)
                if state["token"] or state["errorCode"]:
                    break
                remaining = deadline - monotonic()
                if remaining <= 0:
                    break
                context.timeout = remaining
                context.advance(min(100, remaining * 1000), max_tasks=500)
        except JSError as error:
            record_error(report, error)
        if not context.closed:
            if state is None:
                try:
                    state = context.eval(STATE)
                except JSError as error:
                    record_error(report, error)
            report["consoleErrors"] = [record.get("text", "")[:500]
                                       for record in context.console_log()
                                       if record.get("level") == "error"][:20]
            # Do not export bodies, cookies, query strings or generated widget IDs.
            requests = context.net_log()
            report["network"] = {
                "requestCount": len(requests),
                "apiRequested": any(urlsplit(item.get("url", "")).path ==
                                    "/turnstile/v0/api.js" for item in requests),
                "challengeDocumentRequested": any("/turnstile/f/" in
                                                   urlsplit(item.get("url", "")).path
                                                   for item in requests),
            }
    if state is None:
        report["error"] = "The test page did not expose its callback state"
        return
    token = state.pop("token")
    response_value = state.pop("responseValue")
    status = "passed" if token else "failed" if state["errorCode"] else "timeout"
    report["widget"] = dict(state, status=status, dummyToken=bool(token and "DUMMY" in token),
                            responseFieldMatches=bool(token and response_value == token))
    if token:
        if not report["widget"]["dummyToken"]:
            report["error"] = "Public test key returned an unexpected non-dummy response"
            return
        remaining = deadline - monotonic()
        if remaining <= 0:
            report["error"] = "Deadline reached before Siteverify"
            return
        report["verification"] = verify(token, args.verification, args.proxy, remaining)
        verification_ok = report["verification"]["success"] is (args.verification == "pass")
        if args.verification == "spent":
            verification_ok = verification_ok and "timeout-or-duplicate" in \
                report["verification"].get("error-codes", [])
    else:
        verification_ok = expected_widget == "failed"
    report["ok"] = bool(status == expected_widget and verification_ok and state["apiLoaded"]
                        and not state["pageErrors"] and not report["scriptErrors"]
                        and (not token or report["widget"]["responseFieldMatches"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", choices=SITEKEYS, default="pass")
    parser.add_argument("--verification", choices=SECRETS, default="pass")
    proxy = parser.add_mutually_exclusive_group()
    proxy.add_argument("--proxy", help="Explicit HTTP(S) proxy; default is direct")
    proxy.add_argument("--direct", action="store_true", help="Use direct connections (default)")
    parser.add_argument("--timeout", type=float, default=30, help="Wall-clock budget in seconds")
    parser.add_argument("--output", type=Path, help="Write the diagnostic JSON report")
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be a finite positive number")
    if args.proxy:
        parsed = urlsplit(args.proxy)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or \
                any(c in args.proxy for c in "\0\r\n"):
            parser.error("--proxy must be an HTTP(S) proxy URL")
    report = {"ok": False, "mode": "official-test-keys", "case": args.case,
              "scriptErrors": [], "consoleErrors": [], "verification": None}
    started = monotonic()
    try:
        run(args, report)
    except Exception as error:
        # A proxy URL may include a password; never print it as part of an exception.
        message = str(error).replace(args.proxy, "<proxy>") if args.proxy else str(error)
        report["error"] = type(error).__name__ + ": " + message[:500]
    report["elapsedSeconds"] = round(monotonic() - started, 3)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
