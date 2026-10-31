"""Diagnose the live CapSkip Turnstile demo with the native ruyijs runtime.

Exit 0 requires a non-dummy token and CapSkip's server response reporting
Success=true and Hostname=capskip.com. Challenge failure and timeout exit 1.
"""
import argparse
import copy
import json
import math
import os
from pathlib import Path
import runpy
import sys
from time import monotonic
from urllib.parse import urlsplit

EXAMPLES = Path(__file__).resolve().parents[1]
ROOT = EXAMPLES.parent
if (ROOT / "dist/js").is_file() or (ROOT / "dist/js.exe").is_file():
    sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context, JSError

URL = "https://capskip.com/captcha-demo/cloudflare-turnstile/"

# Expressions run as host code. Page scripts keep their cross-origin and
# closed-root access rules; input goes through the native trusted-input owner.
STATE = r'''(() => {
    const selector = '.captcha-widget[data-provider="turnstile"]';
    const widget = document.querySelector(selector);
    const response = widget?.querySelector('[name="cf-turnstile-response"]')?.value || '';
    const result = {};
    if (widget) for (const row of widget.querySelectorAll('.captcha-result__row')) {
        const key=row.querySelector('dt'), value=row.querySelector('dd');
        if (key && value) result[key.textContent.trim()]=value.textContent.trim();
    }
    function scopes(node, expression) {
        const roots=[{node, expression}];
        for (let i=0; i<roots.length && roots.length<128; i++) {
            const root=roots[i];
            const children=[root.node, ...root.node.querySelectorAll('*')];
            for (let j=0; j<children.length; j++) if (children[j].shadowRoot) {
                const path=j ? root.expression+'.querySelectorAll("*")['+(j-1)+']' : root.expression;
                roots.push({node:children[j].shadowRoot, expression:path+'.shadowRoot'});
            }
        }
        return roots;
    }
    const frames=[];
    if (widget) for (const root of scopes(widget, 'document.querySelector('+JSON.stringify(selector)+')')) {
        for (const [i, frame] of [...root.node.querySelectorAll('*')].entries()) {
            if (frame.localName!=='iframe' || !frame.src.includes('challenges.cloudflare.com/')) continue;
            const expression=root.expression+'.querySelectorAll("*")['+i+']';
            const entry={id:frame.id, url:frame.src};
            const doc=frame.contentDocument;
            if (doc) {
                entry.ready=doc.readyState;
                for (const inner of scopes(doc, expression+'.contentDocument')) {
                    const input=inner.node.querySelector('input[type="checkbox"]');
                    if (!input) continue;
                    const rect=input.getBoundingClientRect();
                    if (rect.width>0 && rect.height>0) {
                        entry.checkbox={target:inner.expression+'.querySelector(\'input[type="checkbox"]\')',
                            rect:rect.toJSON()};
                        break;
                    }
                }
            }
            frames.push(entry);
        }
    }
    return {url:location.href, ready:document.readyState, widget:!!widget,
        sitekey:widget?.querySelector('[data-panel="standard"] [data-sitekey]')?.getAttribute('data-sitekey'),
        classes:widget?.className, status:widget?.querySelector('[data-captcha-status]')?.textContent,
        tokenLength:response.length, dummyToken:response.includes('DUMMY'), result, frames};
})()'''

MONITOR = '''const ruyijsTurnstileEvents=[];
addEventListener('message', e => {
    const d=e.data;
    if (e.origin!=='https://challenges.cloudflare.com' || d?.source!=='cloudflare-challenge' ||
        d.event==='food' || ruyijsTurnstileEvents.length>=64) return;
    ruyijsTurnstileEvents.push({event:d.event,code:d.code,widgetId:d.widgetId,
        tokenLength:typeof d.token==='string' ? d.token.length : 0});
});'''


def configure(context, profile):
    context.configure_clock("system")
    if profile in ("datadome", "linux"):
        example = runpy.run_path(str(EXAMPLES / "DataDome/datadome.py"))
        fingerprint = copy.deepcopy(example["ENVIRONMENT"])
        if profile == "linux":
            fingerprint["navigator"] = {
                "userAgent": "Mozilla/5.0 (X11; Linux x86_64; rv:159.0) Gecko/20100101 Firefox/159.0",
                "platform": "Linux x86_64", "oscpu": "Linux x86_64", "appVersion": "5.0 (X11)",
                "language": "en-US", "languages": ["en-US", "en"],
                "hardwareConcurrency": os.cpu_count() or 1,
            }
            fingerprint["webgl"] = {
                "vendor": "Mozilla", "renderer": "llvmpipe, or similar",
                "unmaskedVendor": "Mesa", "unmaskedRenderer": "llvmpipe, or similar",
            }
        context.configure_fingerprint(fingerprint)
    elif profile == "akamai":
        example = runpy.run_path(str(EXAMPLES / "akamai/akamai.py"))
        fingerprint = copy.deepcopy(example["PROFILE"])
        fingerprint["navigator"]["userAgent"] = fingerprint["navigator"]["userAgent"].replace("158.0", "159.0")
        context.configure_fingerprint(fingerprint)


def read_json(context, expression):
    return json.loads(context.eval("JSON.stringify(" + expression + ")"))


def run(args, report):
    started = monotonic()
    deadline = started + args.timeout
    report.update(url=URL, profile=args.profile, status="timeout", scriptErrors=[],
                  messages=[], clicks=[], states=[], verificationRequests=0)
    with Context(timeout=90, proxy=args.proxy, tls="159") as context:
        configure(context, args.profile)
        context.navigate(URL)
        monitor = False
        clicked = set()
        last_progress = None
        try:
            while monotonic() < deadline:
                context.timeout = min(90, max(0.1, deadline - monotonic()))
                try:
                    context.advance(100, max_tasks=300)
                except JSError as error:
                    entry = {"name": error.name, "message": error.message, "stack": error.stack}
                    if entry not in report["scriptErrors"] and len(report["scriptErrors"]) < 20:
                        report["scriptErrors"].append(entry)
                state = read_json(context, STATE)
                report["state"] = state
                if state["widget"] and not monitor:
                    context.eval(MONITOR)
                    monitor = True
                if monitor:
                    report["messages"] = read_json(context, "ruyijsTurnstileEvents")
                for frame in state["frames"]:
                    checkbox = frame.get("checkbox")
                    if checkbox and frame["url"] not in clicked:
                        context.click(checkbox["target"])
                        clicked.add(frame["url"])
                        report["clicks"].append({"id": frame["id"], "rect": checkbox["rect"],
                                                 "elapsed": round(monotonic() - started, 3)})
                codes = [m["code"] for m in report["messages"] if m.get("event") == "fail" and m.get("code")]
                progress = {"ready": state["ready"], "widget": state["widget"],
                            "frames": len(state["frames"]), "clicks": len(clicked),
                            "tokenLength": state["tokenLength"], "result": state["result"], "codes": codes}
                if progress != last_progress:
                    entry = {"elapsed": round(monotonic() - started, 3), **progress}
                    report["states"].append(entry)
                    print(json.dumps(entry, ensure_ascii=False), flush=True)
                    last_progress = progress
                if (state["tokenLength"] and not state["dummyToken"] and
                        state["result"].get("Success") == "true" and
                        state["result"].get("Hostname") == "capskip.com"):
                    report["status"] = "verified"
                    break
                if codes or "is-error" in state.get("classes", ""):
                    report["status"] = "challenge_failed"
                    break
        except Exception as error:
            report["status"] = "error"
            report["error"] = f"{type(error).__name__}: {error}"
        finally:
            if not context.closed:
                context.timeout = 10
                entries = context.net_log()
                report["verificationRequests"] = sum(
                    entry["method"] == "POST" and urlsplit(entry["url"]).hostname == "capskip.com" and
                    urlsplit(entry["url"]).path == "/wp-admin/admin-ajax.php" and
                    "action=capskip_captcha_verify" in entry.get("requestBody", "") for entry in entries)
                # Keep transport errors, without storing tokens or cookie values.
                report["network"] = [{key: entry[key] for key in ("id", "method", "url", "status", "error")
                                      if key in entry} for entry in entries]
                report["consoleErrors"] = [entry for entry in context.console_log() if entry["level"] == "error"]
            report["elapsed"] = round(monotonic() - started, 3)
    return report["status"] == "verified"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    proxy = parser.add_mutually_exclusive_group()
    proxy.add_argument("--proxy", help="HTTP(S) proxy URL")
    proxy.add_argument("--direct", action="store_true", help="use direct connections")
    parser.add_argument("--profile", choices=("default", "datadome", "akamai", "linux"), default="datadome",
                        help="use an example configuration or the Linux reference environment")
    parser.add_argument("--timeout", type=float, default=180, help="overall attempt budget in seconds")
    parser.add_argument("--output", type=Path, default=Path("cloudflare_result.json"))
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be positive and finite")
    if args.direct:
        args.proxy = None
    elif not args.proxy:
        args.proxy = next((os.environ[name] for name in
                           ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy") if os.environ.get(name)), None)
    report = {}
    try:
        success = run(args, report)
    except Exception as error:
        report.update(status="error", error=f"{type(error).__name__}: {error}")
        success = False
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(args.output)}, ensure_ascii=False), flush=True)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
