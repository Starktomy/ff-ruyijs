# Native iframe compatibility follow-up

The earlier Wine integration notes described an `appendChild` call on a null
mount, a blank iframe under `documentElement`, and a closed shadow root. The
same generic DOM operations run successfully on the native Linux runtime:
the initial blank document has an html/head/body tree, and its Window/Document/
frameElement relationships are consistent. Closed shadow roots remain private
while their connected frames have usable browsing contexts. This does not
reproduce or resolve the old third-party script exception.

The notes also described `window.top` as replaceable. That assumption conflicts
with the [HTML Window interface](https://html.spec.whatwg.org/multipage/nav-history-apis.html#the-window-object):
`top` is readonly and `LegacyUnforgeable`; `parent` and `self` are replaceable.
The existing non-configurable `top` property is correct.

## Reproduced defects and corrections

Local documents exposed three related errors in iframe navigation:

- A `srcdoc` script executed during `appendChild` or the attribute setter. It
  could read parent state before the calling script finished and before its
  microtasks ran. Repeated setters or removal could not prevent its side effects.
- Changing a fallback `src` reloaded an active `srcdoc` document, including an
  empty `srcdoc`, even though the fallback should remain inactive.
- Removing the only `srcdoc` left its document in place instead of navigating
  to an empty `about:blank` document.

`srcdoc` now uses the existing frame navigation queue, completion tokens and
retirement checks. A later source replaces a pending task. Parent document load
waits for the child completion. Removing a frame cancels pending execution;
reinserting it creates a fresh context. Attribute handling preserves `srcdoc`
priority. Blank resets use the inline parser with inherited creator policies
and do not issue an HTTP request. These follow the
[iframe attribute-processing rules](https://html.spec.whatwg.org/multipage/iframe-embed-object.html#process-the-iframe-attributes).

## Regression coverage

`test_iframes.py` exercises seven independent local scenarios: execution order
and microtasks; src/srcdoc replacement; removal and reinsertion; inactive src
changes and empty-srcdoc priority; blank reset and cancellation; parser-created
and closed-shadow children delaying parent load; and blank-document identity.
The first four ordering/cancellation tests failed before the queue fix. The
attribute tests separately reproduced the two remaining defects before their
fixes. All seven pass on the updated runtime, using a logical clock.

```bash
python3 -B -m unittest discover -s native_tests -p test_iframes.py -v
```

`installed_probe.py` also checks deferred execution, replacement, closed-shadow
frames, inactive fallback changes and blank reset through an installed wheel,
outside the checkout with runtime/source overrides removed.

## Cloudflare observation limits

Public dummy-key integration is covered by `examples/cloudflare/turnstile.py`.
The official forced-interaction test key was separately observed for 15 seconds
on the preceding runtime: the live API and widget document returned HTTP 200,
with no recorded script/console errors, and no completion callback arrived.
No human interaction was performed, so that observation is not a solve result
or evidence that the widget could complete an interactive challenge.

The runtime fixes above come from local standards-oriented reproductions. They
do not establish acceptance by production anti-bot services, repair the original
solver protocol, or prove the historical Wine null-mount exception is fixed.
