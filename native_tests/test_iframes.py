"""Local iframe lifecycle tests, independent of third-party widget scripts."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context

SHELL = ROOT / "dist/js"
URL = "https://frames.test/"


@unittest.skipUnless(SHELL.is_file(), "build the native runtime first")
class IframeLifecycleTests(unittest.TestCase):
    def context(self):
        context = Context(shell=SHELL, timeout=10)
        self.addCleanup(context.close)
        context.configure_clock("logical", epoch_ms=1700000000000)
        context.load_page(URL, "<!doctype html><html><head></head><body></body></html>")
        return context

    def test_srcdoc_waits_for_parent_script_and_microtasks(self):
        context = self.context()
        context.set("markup", "<script>parent.order.push('child:' + parent.marker)</script>"
                    "<main id='child'>ready</main>")
        before = context.eval("""window.order = []; window.marker = 'early';
            window.frame = document.createElement('iframe'); frame.srcdoc = markup;
            frame.onload = () => order.push('load'); document.body.appendChild(frame);
            order.push('append-return'); marker = 'ready';
            queueMicrotask(() => order.push('microtask'));
            ({order: order.slice(), url: frame.contentDocument.URL,
              body: !!frame.contentDocument.body, child: !!frame.contentDocument.getElementById('child')})""")
        self.assertEqual(before, {"order": ["append-return"], "url": "about:blank",
                                  "body": True, "child": False})
        self.assertEqual(context.eval("order"), ["append-return", "microtask"])
        context.advance(0)
        self.assertEqual(context.eval("order"),
                         ["append-return", "microtask", "child:ready", "load"])
        self.assertEqual(context.eval("frame.contentDocument.URL"), "about:srcdoc")
        self.assertEqual(context.eval("frame.contentDocument.getElementById('child').textContent"), "ready")

    def test_replaced_srcdoc_and_src_share_cancellation(self):
        context = self.context()
        external = URL + "external.html"
        context.put_resource(external, "<script>parent.order.push('external')</script>")
        context.set("first", "<script>parent.order.push('first')</script>")
        context.set("latest", "<script>parent.order.push('latest')</script>")
        context.eval("""window.order = []; window.frame = document.createElement('iframe');
            frame.src = '/external.html'; document.body.appendChild(frame);
            frame.srcdoc = first; frame.srcdoc = latest; void 0;""")
        self.assertEqual(context.eval("order"), [])
        context.advance(0)
        self.assertEqual(context.eval("order"), ["latest"])
        self.assertFalse(any(item["url"] == external for item in context.net_log()))
        # Removing srcdoc activates the already configured external src.
        context.eval("frame.removeAttribute('srcdoc')")
        self.assertEqual(context.eval("order"), ["latest"])
        context.advance(0)
        self.assertEqual(context.eval("order"), ["latest", "external"])
        self.assertEqual(context.eval("frame.contentDocument.URL"), external)

    def test_removal_cancels_pending_srcdoc_and_reinsertion_uses_new_context(self):
        context = self.context()
        context.set("oldMarkup", "<script>parent.order.push('removed')</script>")
        context.set("newMarkup", "<script>parent.order.push('reinserted')</script>")
        context.eval("""window.order = []; window.frame = document.createElement('iframe');
            frame.srcdoc = oldMarkup; document.body.appendChild(frame);
            window.oldWindow = frame.contentWindow; frame.remove(); void 0;""")
        context.advance(0)
        self.assertEqual(context.eval("order"), [])
        self.assertTrue(context.eval("frame.contentWindow === null"))
        context.eval("frame.srcdoc = newMarkup; document.body.appendChild(frame); void 0;")
        self.assertTrue(context.eval("frame.contentWindow !== oldWindow"))
        self.assertEqual(context.eval("order"), [])
        context.advance(0)
        self.assertEqual(context.eval("order"), ["reinserted"])

    def test_src_changes_do_not_reload_an_active_srcdoc(self):
        context = self.context()
        context.set("markup", "<script>parent.order.push('srcdoc')</script>")
        context.eval("""window.order = []; window.frame = document.createElement('iframe');
            frame.srcdoc = markup; document.body.appendChild(frame); void 0;""")
        context.advance(0)
        self.assertEqual(context.eval("order"), ["srcdoc"])
        context.eval("frame.src = '/unused.html'; frame.setAttribute('src', '/other.html'); void 0;")
        context.advance(0)
        self.assertEqual(context.eval("order"), ["srcdoc"])
        self.assertEqual(context.net_log(), [])
        # A present empty srcdoc also takes priority over src.
        context.eval("frame.srcdoc = ''; frame.src = '/unused.html'; void 0;")
        context.advance(0)
        self.assertEqual(context.eval("[frame.contentDocument.URL, frame.contentDocument.body.innerHTML]"),
                         ["about:srcdoc", ""])
        self.assertEqual(context.net_log(), [])

    def test_removing_srcdoc_without_src_navigates_to_blank(self):
        context = self.context()
        context.eval("""window.frame = document.createElement('iframe');
            frame.srcdoc = '<main>old</main>'; document.body.appendChild(frame); void 0;""")
        context.advance(0)
        self.assertEqual(context.eval("frame.contentDocument.body.textContent"), "old")
        context.eval("frame.removeAttribute('srcdoc')")
        self.assertEqual(context.eval("frame.contentDocument.URL"), "about:srcdoc")
        context.advance(0)
        self.assertEqual(context.eval("""[frame.contentDocument.URL,
            frame.contentDocument.body.innerHTML, frame.contentWindow.parent === window]"""),
                         ["about:blank", "", True])
        self.assertEqual(context.net_log(), [])
        # Clearing srcdoc before its pending navigation runs cancels that markup.
        context.eval("""window.hit = false;
            frame.srcdoc = '<script>parent.hit = true<\\/script>';
            frame.removeAttribute('srcdoc'); void 0;""")
        context.advance(0)
        self.assertEqual(context.eval("[hit, frame.contentDocument.URL]"), [False, "about:blank"])

    def test_parser_and_closed_shadow_frames_delay_parent_load(self):
        context = self.context()
        context.load_page(URL, """<!doctype html><html><head><script>
            window.order = []; addEventListener('load', () => order.push('parent-load'));
            </script></head><body>
            <iframe srcdoc="<script>parent.order.push('parser-child')</script>"></iframe>
            <script>order.push('parent-ready');
            const host = document.createElement('div'); const root = host.attachShadow({mode:'closed'});
            const child = document.createElement('iframe');
            child.srcdoc = '<script>parent.order.push("shadow-child")<\\/script>';
            root.appendChild(child); document.body.appendChild(host);
            order.push('shadow-return');</script></body></html>""")
        self.assertEqual(context.eval("order"),
                         ["parent-ready", "shadow-return", "parser-child", "shadow-child", "parent-load"])
        self.assertEqual(context.eval("document.readyState"), "complete")

    def test_blank_frame_and_closed_shadow_identity(self):
        context = self.context()
        context.eval("""window.host = document.createElement('div');
            window.root = host.attachShadow({mode:'closed'}); document.body.appendChild(host);
            window.frame = document.createElement('iframe'); root.appendChild(frame);
            frame.contentDocument.body.appendChild(frame.contentDocument.createElement('main'));
            void 0;""")
        self.assertEqual(context.eval("""({hidden: host.shadowRoot === null,
            body: frame.contentDocument.body.innerHTML,
            document: frame.contentWindow.document === frame.contentDocument,
            view: frame.contentDocument.defaultView === frame.contentWindow,
            element: frame.contentWindow.frameElement === frame,
            parent: frame.contentWindow.parent === window,
            top: frame.contentWindow.top === top,
            topConfigurable: Object.getOwnPropertyDescriptor(window, 'top').configurable})"""),
                         {"hidden": True, "body": "<main></main>", "document": True,
                          "view": True, "element": True, "parent": True, "top": True,
                          "topConfigurable": False})


if __name__ == "__main__":
    unittest.main()
