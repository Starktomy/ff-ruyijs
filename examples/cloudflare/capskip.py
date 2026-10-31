"""Run the live CapSkip Turnstile demo and wait for its server verification.

python -m ruyijs.examples cloudflare-live
python -m ruyijs.examples cloudflare-live --timeout 180 --output artifacts/capskip.json
python -m ruyijs.examples cloudflare-live --profile akamai --interaction trajectory

The original page and challenge scripts run in Context. When Cloudflare requests
interaction, native input clicks the checkbox inside its frame and shadow tree.
Success requires the demo's backend verification, not merely a loaded widget.
"""

import argparse
from collections import Counter
import copy
from functools import lru_cache
import importlib.util
import json
import math
from pathlib import Path
import sys
from time import monotonic
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]
if (ROOT / "python/ruyijs/__init__.py").is_file():
    sys.path.insert(0, str(ROOT / "python"))

from ruyijs import Context, JSError

URL = "https://capskip.com/captcha-demo/cloudflare-turnstile/"
CHECKBOX = 'input[type="checkbox"]'
OBSERVER = """const capskipChallengeErrors = [];
addEventListener('message', event => {
  const data = event.data;
  if (event.origin === 'https://challenges.cloudflare.com' && data &&
      data.source === 'cloudflare-challenge' && data.event === 'fail') {
    if (capskipChallengeErrors.length < 20)
      capskipChallengeErrors.push(String(data.code || 'unknown'));
  }
});"""
STATE = """(() => {
  const widget = document.querySelector('.captcha-widget[data-provider="turnstile"]');
  const field = document.querySelector('[name="cf-turnstile-response"]');
  const token = field && field.value || '';
  const result = widget ? Object.fromEntries(
    [...widget.querySelectorAll('.captcha-result__row')].map(row => [
      row.querySelector('dt').textContent, row.querySelector('dd').textContent
    ]).filter(([key]) => key !== 'Token')) : {};
  return {
    url: location.href, readyState: document.readyState, widgetLoaded: !!widget,
    apiLoaded: typeof turnstile === 'object',
    sitekey: widget && widget.getAttribute('data-sitekey'),
    status: widget && widget.querySelector('[data-captcha-status]').textContent || '',
    verified: !!widget && widget.classList.contains('is-verified'),
    failed: !!widget && widget.classList.contains('is-error'),
    tokenLength: token.length, dummyToken: token.includes('DUMMY'), result,
    challengeErrors: typeof capskipChallengeErrors === 'undefined' ? [] : capskipChallengeErrors
  };
})()"""


@lru_cache(maxsize=2)
def reference_example(name):
    relative = {"akamai": "akamai/akamai.py", "datadome": "DataDome/datadome.py"}[name]
    path = Path(__file__).resolve().parent.parent / relative
    spec = importlib.util.spec_from_file_location("ruyijs_reference_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fingerprint(args):
    if args.profile == "akamai":
        profile = copy.deepcopy(reference_example("akamai").PROFILE)
    elif args.profile == "datadome":
        profile = copy.deepcopy(reference_example("datadome").ENVIRONMENT)
    else:
        profile = {}
    # The presets use Firefox on Windows; keep the browser and TLS versions
    # together, as the Akamai example does.
    profile.setdefault("navigator", {})["userAgent"] = (
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:{args.tls}.0) "
        f"Gecko/20100101 Firefox/{args.tls}.0")
    return profile


def approach_checkbox(context, frame, deadline, report):
    environment = context.eval_in_frame(
        "({width:innerWidth,height:innerHeight,x:mozInnerScreenX,y:mozInnerScreenY})", frame)
    trajectory = reference_example("akamai").gen_trajectory(
        environment["width"], environment["height"], 30)
    for x, y, duration in trajectory:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError("Deadline reached during pointer interaction")
        context.timeout = remaining
        for kind in ("pointerrawupdate", "pointermove", "mousemove"):
            context.dispatch_input(kind, frame=frame, target="document.documentElement",
                                   clientX=x, clientY=y,
                                   screenX=x + environment["x"], screenY=y + environment["y"],
                                   button=-1 if kind.startswith("pointer") else 0, buttons=0,
                                   pointerId=0, pointerType="mouse", isPrimary=True, width=1, height=1)
            report["pointerEvents"] += 1
        if duration > 0:
            context.advance(min(duration, max(0, (deadline - monotonic()) * 1000)), max_tasks=100)


def challenge_frame(frame):
    url = urlsplit(frame["url"])
    return (url.scheme == "https" and url.hostname == "challenges.cloudflare.com"
            and "/turnstile/f/" in url.path)


def run(args, report):
    deadline = monotonic() + args.timeout
    with Context(proxy=args.proxy, timeout=args.timeout, tls=args.tls) as context:
        context.configure_clock("system")
        context.configure_fingerprint(fingerprint(args))
        report["transport"] = context.transport
        report["tls"] = context.tls
        context.navigate(URL)
        observed = False
        clicked = set()
        while monotonic() < deadline:
            context.timeout = max(0.1, deadline - monotonic())
            try:
                # Return between tasks so theme/analytics work does not prevent
                # the host from noticing an interactive widget as it appears.
                context.advance(100, max_tasks=1)
            except JSError as error:
                if len(report["scriptErrors"]) < 20:
                    report["scriptErrors"].append({"name": error.name, "message": error.message[:500]})
            state = context.eval(STATE)
            report["page"] = state
            if state["widgetLoaded"] and not observed:
                context.eval(OBSERVER)
                observed = True
            report["tokenLength"] = max(report["tokenLength"], state["tokenLength"])
            if state["verified"]:
                report["ok"] = bool(state["result"].get("Success") == "true"
                                    and state["result"].get("Hostname") == "capskip.com"
                                    and report["tokenLength"] > 0 and not state["dummyToken"])
                if not report["ok"]:
                    report["error"] = "The demo did not confirm a real token for capskip.com"
                break
            if state["failed"]:
                report["error"] = state["status"] or "Turnstile challenge failed"
                break
            for frame in context.frames():
                if not challenge_frame(frame) or frame["url"] in clicked:
                    continue
                try:
                    box = context.element_rect(frame["path"], CHECKBOX)
                    if box["present"] and box["width"] > 0 and box["height"] > 0:
                        if args.interaction == "trajectory":
                            approach_checkbox(context, frame["path"], deadline, report)
                        context.click(frame=frame["path"], selector=CHECKBOX)
                        clicked.add(frame["url"])
                        report["checkboxClicks"] += 1
                except JSError as error:
                    # A frame can be replaced while the event loop is running.
                    if "Selector matched no element" not in error.message and \
                            "Frame path does not address a live child frame" not in error.message:
                        raise
        else:
            report["error"] = "Deadline reached before the demo confirmed verification"
        if not context.closed:
            report["page"] = context.eval(STATE)
            requests = context.net_log()
            report["network"] = {
                "requestCount": len(requests),
                "statusCounts": dict(Counter(str(item["status"]) for item in requests)),
                "challengeDocumentRequested": any(challenge_frame(item) for item in requests),
                "verificationRequests": sum(
                    urlsplit(item["url"]).hostname == "capskip.com"
                    and urlsplit(item["url"]).path == "/wp-admin/admin-ajax.php"
                    and parse_qs(item.get("requestBody", "")).get("action") == ["capskip_captcha_verify"]
                    for item in requests),
            }
            report["consoleErrors"] = [item["text"][:500] for item in context.console_log()
                                       if item["level"] == "error"][:20]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    proxy = parser.add_mutually_exclusive_group()
    proxy.add_argument("--proxy", help="Explicit HTTP(S) proxy URL")
    proxy.add_argument("--direct", action="store_true", help="Use direct connections (default)")
    parser.add_argument("--timeout", type=float, default=180, help="Wall-clock budget in seconds")
    parser.add_argument("--profile", choices=("default", "akamai", "datadome"), default="default",
                        help="Reuse a repository example's Firefox fingerprint configuration")
    parser.add_argument("--interaction", choices=("click", "trajectory"), default="click",
                        help="Add the Akamai example's timed pointer trajectory before clicking")
    parser.add_argument("--tls", default="159", help="Matching Firefox TLS/User-Agent version (100-159)")
    parser.add_argument("--output", type=Path, help="Write the diagnostic JSON report")
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be a finite positive number")
    if args.proxy:
        url = urlsplit(args.proxy)
        if url.scheme not in ("http", "https") or not url.hostname or \
                any(c in args.proxy for c in "\0\r\n"):
            parser.error("--proxy must be an HTTP(S) proxy URL")
    report = {"ok": False, "url": URL, "mode": "live-page", "checkboxClicks": 0,
              "profile": args.profile, "interaction": args.interaction, "pointerEvents": 0,
              "tokenLength": 0, "scriptErrors": [], "consoleErrors": []}
    started = monotonic()
    try:
        run(args, report)
    except Exception as error:
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
