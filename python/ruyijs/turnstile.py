"""Solve a Cloudflare Turnstile challenge for a known site URL and sitekey."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re
import sys
from time import monotonic
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from ._context import Context
from ._values import JSError


_ACTION = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")
_SITEKEY = re.compile(r"^[0-9A-Za-z_-]{16,255}$")


class TurnstileError(RuntimeError):
    """Turnstile did not produce a non-dummy token."""

    def __init__(self, message: str, *, code: str | None = None,
                 events: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.code = code
        self.events = list(events or [])


@dataclass(frozen=True)
class TurnstileSolution:
    token: str
    elapsed: float
    attempts: int


def _validated_url(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("site_url must be a string")
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("site_url must be an absolute http(s) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("site_url must not contain credentials")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))


def _linux_profile() -> dict[str, Any]:
    path = Path(__file__).with_name("turnstile_linux_profile.json")
    profile = json.loads(path.read_text(encoding="utf-8"))
    profile["navigator"]["hardwareConcurrency"] = min(os.cpu_count() or 1, 32)
    return profile


def _page() -> str:
    return """<!doctype html><html><head><meta name=viewport
      content="width=device-width,initial-scale=1"><title>Sign in</title></head><body>
      <div id=turnstile-target></div><script>
      globalThis.ruyijsTurnstile={token:'',error:'',timedOut:false,rendered:false,
        events:[],clicks:0};
      function ruyijsToken(value){ruyijsTurnstile.token=value;
        ruyijsTurnstile.events.push({event:'token',length:value.length})}
      function ruyijsError(code){ruyijsTurnstile.error=String(code);
        ruyijsTurnstile.events.push({event:'error',code:String(code)})}
      function ruyijsExpired(){ruyijsTurnstile.events.push({event:'expired'})}
      function ruyijsTimeout(){ruyijsTurnstile.timedOut=true;
        ruyijsTurnstile.events.push({event:'timeout'})}
      </script><script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async>
      </script></body></html>""".replace("\n", " ")


_STATE = r'''(() => {
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
  const targets=[];
  for (const root of scopes(document, 'document')) {
    const children=[root.node, ...root.node.querySelectorAll('*')];
    for (const [i, frame] of children.entries()) {
      if (!frame.localName || frame.localName!=='iframe' ||
          !String(frame.src||'').includes('challenges.cloudflare.com/')) continue;
      const framePath=i ? root.expression+'.querySelectorAll("*")['+(i-1)+']' : root.expression;
      const doc=frame.contentDocument;
      if (!doc) continue;
      for (const inner of scopes(doc, framePath+'.contentDocument')) {
        const nodes=[inner.node, ...inner.node.querySelectorAll('*')];
        for (const [j, input] of nodes.entries()) {
          if (input.localName!=='input' || input.type!=='checkbox') continue;
          const rect=input.getBoundingClientRect();
          if (rect.width>0 && rect.height>0) {
            const path=j ? inner.expression+'.querySelectorAll("*")['+(j-1)+']' : inner.expression;
            targets.push(path);
          }
        }
      }
    }
  }
  return {ready:document.readyState, rendered:ruyijsTurnstile.rendered,
    tokenLength:ruyijsTurnstile.token.length, error:ruyijsTurnstile.error,
    timedOut:ruyijsTurnstile.timedOut, events:ruyijsTurnstile.events,
    api:typeof turnstile!=='undefined', frames:document.querySelectorAll('iframe').length,
    targets};
})()'''


def _render_options(sitekey: str, action: str | None, cdata: str | None) -> dict[str, Any]:
    options: dict[str, Any] = {
        "sitekey": sitekey,
        "callback": "ruyijsToken",
        "error-callback": "ruyijsError",
        "expired-callback": "ruyijsExpired",
        "timeout-callback": "ruyijsTimeout",
        "theme": "light",
        "size": "normal",
        "appearance": "always",
        "language": "auto",
        "retry": "auto",
    }
    if action is not None:
        options["action"] = action
    if cdata is not None:
        options["cData"] = cdata
    return options


def _solve_once(site_url: str, sitekey: str, *, action: str | None, cdata: str | None,
                timeout: float, proxy: str | None, profile: dict[str, Any] | None,
                shell: str | Path | None, poll_ms: int) -> TurnstileSolution:
    started = monotonic()
    events: list[dict[str, Any]] = []
    script_errors: list[str] = []
    clicked: set[str] = set()
    rendered = False
    options = _render_options(sitekey, action, cdata)

    with Context(shell=shell, timeout=min(30, timeout), proxy=proxy, tls="159") as context:
        context.configure_clock("system")
        if profile is not None:
            context.configure_fingerprint(profile)
        context.load_page(site_url, _page())
        while monotonic() - started < timeout:
            remaining = timeout - (monotonic() - started)
            context.timeout = min(30, max(0.2, remaining))
            try:
                context.advance(poll_ms, max_tasks=400)
            except JSError as error:
                script_errors.append(error.message)
            state = json.loads(context.eval("JSON.stringify(" + _STATE + ")"))
            events = state.get("events", [])
            if not rendered and state.get("api"):
                encoded = json.dumps(options, separators=(",", ":"))
                for callback in ("ruyijsToken", "ruyijsError", "ruyijsExpired", "ruyijsTimeout"):
                    encoded = encoded.replace(json.dumps(callback), callback)
                context.eval("ruyijsTurnstile.widgetId=turnstile.render('#turnstile-target'," +
                             encoded + ");ruyijsTurnstile.rendered=true")
                rendered = True
                continue
            for target in state.get("targets", []):
                if target not in clicked:
                    clicked.add(target)
                    context.eval("ruyijsTurnstile.clicks++")
                    context.click(target)
            if state.get("error"):
                raise TurnstileError(f"Turnstile error {state['error']}",
                                     code=state["error"], events=events)
            if state.get("tokenLength"):
                token = context.eval("ruyijsTurnstile.token")
                if not isinstance(token, str) or len(token) < 200 or "DUMMY" in token:
                    raise TurnstileError("Turnstile returned an invalid token", events=events)
                return TurnstileSolution(token, monotonic() - started, 1)

    code = "timeout"
    message = "Turnstile timed out before returning a token"
    if script_errors:
        message += f"; last script error: {script_errors[-1]}"
        code = "script-error"
    raise TurnstileError(message, code=code, events=events)


def solve_turnstile_details(site_url: str, sitekey: str, *, action: str | None = None,
                            cdata: str | None = None, timeout: float = 90.0,
                            attempts: int = 3, poll_ms: int = 100,
                            proxy: str | None = None,
                            profile: dict[str, Any] | str | None = "linux",
                            shell: str | Path | None = None) -> TurnstileSolution:
    """Return a non-dummy Turnstile token and timing details.

    ``site_url`` must use the hostname registered for ``sitekey``. The path and
    query are preserved so location-sensitive sitekeys behave as on the target
    page. Each attempt uses a fresh Context; no cookie jar or token is reused.
    """
    site_url = _validated_url(site_url)
    if not isinstance(sitekey, str) or not _SITEKEY.fullmatch(sitekey):
        raise ValueError("sitekey must contain 16-255 URL-safe characters")
    if action is not None and (not isinstance(action, str) or not _ACTION.fullmatch(action)):
        raise ValueError("action must be 1-32 letters, digits, underscores or hyphens")
    if cdata is not None:
        if not isinstance(cdata, str) or not cdata or len(cdata) > 255:
            raise ValueError("cdata must be a nonempty string of at most 255 characters")
        if any(character in cdata for character in "\x00\r\n"):
            raise ValueError("cdata must not contain NUL, CR or LF")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be a finite positive number")
    if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 1:
        raise ValueError("attempts must be a positive integer")
    if isinstance(poll_ms, bool) or not isinstance(poll_ms, int) or not 20 <= poll_ms <= 1000:
        raise ValueError("poll_ms must be an integer from 20 to 1000")

    if profile == "linux":
        configured = _linux_profile()
    elif profile in (None, "default"):
        configured = None
    elif isinstance(profile, dict):
        configured = profile
    else:
        raise ValueError("profile must be 'linux', 'default', None, or a fingerprint dictionary")

    started = monotonic()
    last_error: TurnstileError | None = None
    for attempt in range(1, attempts + 1):
        try:
            solution = _solve_once(site_url, sitekey, action=action, cdata=cdata,
                                   timeout=timeout, proxy=proxy, profile=configured,
                                   shell=shell, poll_ms=poll_ms)
            return TurnstileSolution(solution.token, monotonic() - started, attempt)
        except TurnstileError as error:
            last_error = error
        except JSError as error:
            last_error = TurnstileError(f"Script error: {error.message}",
                                        code="script-error")
    assert last_error is not None
    raise last_error


def solve_turnstile(site_url: str, sitekey: str, *, action: str | None = None,
                    cdata: str | None = None, timeout: float = 90.0,
                    attempts: int = 3, poll_ms: int = 100,
                    proxy: str | None = None,
                    profile: dict[str, Any] | str | None = "linux",
                    shell: str | Path | None = None) -> str:
    """Return only a non-dummy Turnstile token string."""
    return solve_turnstile_details(site_url, sitekey, action=action, cdata=cdata,
                                   timeout=timeout, attempts=attempts, poll_ms=poll_ms,
                                   proxy=proxy, profile=profile, shell=shell).token


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site_url", help="URL whose hostname is registered for the sitekey")
    parser.add_argument("sitekey")
    parser.add_argument("--action")
    parser.add_argument("--cdata")
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--poll-ms", type=int, default=100)
    proxy = parser.add_mutually_exclusive_group()
    proxy.add_argument("--proxy", help="HTTP(S) proxy URL")
    proxy.add_argument("--direct", action="store_true", help="ignore proxy environment variables")
    parser.add_argument("--profile", choices=("linux", "default"), default="linux")
    parser.add_argument("--json", action="store_true",
                        help="print token, timing and attempts as JSON")
    args = parser.parse_args(argv)

    selected_proxy = None if args.direct else (args.proxy or next((
        os.environ[name] for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy")
        if os.environ.get(name)), None))
    try:
        solution = solve_turnstile_details(
            args.site_url, args.sitekey, action=args.action, cdata=args.cdata,
            timeout=args.timeout, attempts=args.attempts, poll_ms=args.poll_ms,
            proxy=selected_proxy, profile=args.profile)
    except (ValueError, TypeError, TurnstileError) as error:
        print(str(error), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"token": solution.token, "elapsed": round(solution.elapsed, 3),
                          "attempts": solution.attempts}))
    else:
        print(solution.token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
