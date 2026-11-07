# Minimal kernel validation, 2026-11-07

This main starts from upstream 0.3.5, commit
`0ab720142361ed2fafd42224f2c2772dc5d1f219`. The previous full fork is preserved
locally and remotely as `backup/main-full-20261107` at `158eae7`.

The native changes are Trusted Types default-policy conversions at HTML,
Script and ScriptURL sinks (with the JSAPI include and per-thread registries),
host inspection of closed shadow roots, and iframe input coordinates/focus.
They expose general browser behavior. Provider solvers, profiles and application
APIs belong in the surrounding application; their previous sources remain on
the backup branch.

The rebuilt Linux x86_64 runtime passes all nine focused native tests with no
skips, plus upstream smoke, layout, atob, direct networking and Engine network
checks. The Engine check includes independent direct and proxy sessions.
Windows and macOS were not built in this validation.

The original CapSkip page passes backend verification in three fresh direct
Contexts: 110.010, 107.992 and 110.261 seconds. Tokens were 624–645 characters,
with Success=true and Hostname=capskip.com. Each report captured one verification
POST and no surfaced JSError. No checkbox click was required in these samples.

The retained external driver also tests the original `site_url + sitekey`
solver against this kernel, without loading the complete target page:

| Batch | Token acquisition seconds | Backend acceptance |
| --- | --- | --- |
| Initial three runs | 3.993 / 3.915 / 3.914 | 3/3 |
| Explicit sitekey + URL confirmation | 3.869 / 3.783 / 4.020 | 3/3 |

These times exclude backend submission. Both batches used a real CapSkip
sitekey, Linux Firefox 159 profile, system clock and a fresh Context per call.
Backend responses were HTTP 200 with verified=true, server=true, success=true
and hostname=capskip.com. Responses and diagnostics retain token lengths,
not response tokens, cookies or verification request bodies.

The full-page route remains much slower than the minimal widget route. A bounded
diagnostic sampled 47.37 process-tree CPU seconds over 44.142 wall seconds; this
is a CPU-heavy workload. The diagnostic was deliberately interrupted and is
excluded from success counts. Performance work needs independent measurement
and browser-behavior regressions; it is separate from the compatibility result.

The runtime SHA256 is
`66d41abd93a1cddfd4e4d1bed62321cef9058030a4cf26a0716d027804443bca`.
Evidence is in the ignored directory `artifacts/minimal-cloudflare-20261107/`;
raw live reports are in `artifacts/upstream-latest-20261107/` with labels
`minimal-final-20261107` and `sitekey-surl-confirm-20261107`.
The retained input scripts are under
`artifacts/minimal-cloudflare-20261107/original-drivers/`.
