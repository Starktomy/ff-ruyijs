"""Document navigation replaces an iframe's inner Window, preserving its proxy."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class IframeNavigationTests(unittest.TestCase):
    def context(self):
        return Context(shell=ROOT / "dist/js", timeout=10)

    def test_navigation_replaces_globals_document_and_old_tasks(self):
        with self.context() as c:
            c.put_resource('https://frame.test/a', '''<!doctype html><title>A</title><script>
                let imageLoaded=true;globalThis.oldOnly=1;parent.events.push('a');
                setTimeout(()=>parent.events.push('old timer'),200);
                document.addEventListener('DOMContentLoaded',()=>parent.events.push('a ready'));
            </script>''')
            c.put_resource('https://frame.test/b', '''<!doctype html><title>B</title><script>
                let imageLoaded=false;globalThis.newOnly=2;parent.events.push('b');
                setTimeout(()=>parent.events.push('new timer'),30);
            </script>''')
            c.load_page('https://frame.test/', '''<!doctype html><script>globalThis.events=[]</script>
                <iframe id="f" src="/a"></iframe>''')
            c.eval("globalThis.held=f.contentWindow;globalThis.oldDoc=f.contentDocument;f.src='/b'")
            self.assertEqual(c.eval('held.document.title'), 'A')
            c.advance(10)
            c.collect_garbage()
            self.assertEqual(c.eval('''[held===f.contentWindow,held.document!==oldDoc,
                typeof held.oldOnly,held.newOnly,held.document.title,
                held.eval('window===globalThis && this===window && document.defaultView===window')]'''),
                [True, True, 'undefined', 2, 'B', True])
            c.advance(300)
            self.assertEqual(c.eval('events'), ['a', 'a ready', 'b', 'new timer'])

    def test_srcdoc_is_async_cancellable_and_ignores_inactive_src_changes(self):
        with self.context() as c:
            c.put_resource('https://frame.test/fallback', '<!doctype html><title>Fallback</title>')
            c.load_page('https://frame.test/', '<!doctype html><script>globalThis.events=[]</script>')
            c.eval(r'''globalThis.f=document.createElement('iframe');
                f.src='/fallback';f.srcdoc='<script>let imageLoaded=true;parent.events.push("first")<\/script>';
                document.body.appendChild(f);globalThis.held=f.contentWindow;
                globalThis.before=events.slice();''')
            self.assertEqual(c.eval('before'), [])
            c.advance(10)
            self.assertEqual(c.eval('events'), ['first'])
            c.eval("f.src='/fallback?inactive'")
            c.advance(10)
            self.assertEqual(c.eval('events'), ['first'])
            c.eval(r'''f.src='/fallback';
                f.srcdoc='<script>let imageLoaded=false;parent.events.push("cancelled")<\/script>';
                f.srcdoc='<script>let imageLoaded=false;parent.events.push("last")<\/script>';''')
            c.advance(10)
            self.assertEqual(c.eval('events'), ['first', 'last'])
            c.eval("f.removeAttribute('srcdoc')")
            c.advance(10)
            self.assertEqual(c.eval('[held===f.contentWindow,held.document.title]'), [True, 'Fallback'])
            c.eval("f.removeAttribute('src')")
            c.advance(10)
            self.assertEqual(c.eval('[held.location.href,held.document.body.textContent]'), ['about:blank', ''])
            self.assertFalse(any('inactive' in row['url'] for row in c.net_log()))

    def test_held_proxy_rechecks_origin_after_each_navigation(self):
        with self.context() as c:
            c.put_resource('https://parent.test/a', '<!doctype html><script>globalThis.secret="same"</script>')
            c.put_resource('https://other.test/b', '<!doctype html><script>globalThis.secret="cross"</script>')
            c.load_page('https://parent.test/', '''<!doctype html><script>
                function inspect(){try{return held.secret}catch(e){return e.name}}
                function inspectDocument(){return document.querySelector('iframe').contentDocument===null}
                </script><iframe id="f" src="/a"></iframe>''')
            c.eval('globalThis.held=f.contentWindow;void 0')
            self.assertEqual(c.eval('inspect()'), 'same')
            c.eval("f.src='https://other.test/b'")
            c.advance(10)
            self.assertEqual(c.eval('[held===f.contentWindow,inspect(),inspectDocument(),held.secret]'),
                             [True, 'SecurityError', True, 'cross'])
            c.eval("f.src='/a'")
            c.advance(10)
            self.assertEqual(c.eval('[held===f.contentWindow,inspect(),inspectDocument()]'), [True, 'same', False])

    def test_descendant_tasks_are_retired_with_the_navigating_document(self):
        with self.context() as c:
            c.put_resource('https://frame.test/a', '<!doctype html><iframe src="/nested"></iframe>')
            c.put_resource('https://frame.test/nested', '''<!doctype html><script>
                setTimeout(()=>top.events.push('nested timer'),200)</script>''')
            c.put_resource('https://frame.test/b', '<!doctype html><title>B</title>')
            c.load_page('https://frame.test/', '''<!doctype html><script>globalThis.events=[]</script>
                <iframe id="f" src="/a"></iframe>''')
            self.assertEqual(c.eval('f.contentWindow.length'), 1)
            c.eval("f.src='/b'")
            c.advance(300)
            self.assertEqual(c.eval('[f.contentWindow.length,f.contentDocument.title,events]'), [0, 'B', []])

    def test_no_content_response_keeps_the_current_document(self):
        with self.context() as c:
            c.put_resource('https://frame.test/a', '''<!doctype html><title>A</title><script>
                setTimeout(()=>parent.fired=true,100)</script>''')
            c.put_resource('https://frame.test/empty', '', status=204)
            c.load_page('https://frame.test/', '<!doctype html><iframe id="f" src="/a"></iframe>')
            c.eval("globalThis.oldDoc=f.contentDocument;f.src='/empty'")
            c.advance(200)
            self.assertEqual(c.eval('[oldDoc===f.contentDocument,f.contentDocument.title,fired]'), [True, 'A', True])

    def test_window_receivers_events_and_globals_use_one_proxy(self):
        with self.context() as c:
            c.load_page('https://frame.test/', '<!doctype html><iframe></iframe>')
            self.assertTrue(c.eval('''(() => {
                let valid=false;
                window.addEventListener('check', function(e) {'use strict';
                    valid=this===window && e.target===window && e.currentTarget===window && e.composedPath()[0]===window;
                });
                window.dispatchEvent(new Event('check'));
                const d=Object.getOwnPropertyDescriptor(window,'top');
                let topWrite;
                try{(()=>{'use strict';window.top={}})()}catch(e){topWrite=e.name}
                return valid && window===globalThis && window===this && window===frames &&
                    window instanceof Window && Object.getPrototypeOf(window)===Window.prototype &&
                    window===document.defaultView && frames[0]===document.querySelector('iframe').contentWindow &&
                    frames[0].eval('this===window && window===globalThis') &&
                    !d.configurable && d.set===undefined && topWrite==='TypeError';
            })()'''))

    def test_removed_frame_cancels_queued_navigation_and_reinsertion_gets_new_proxy(self):
        with self.context() as c:
            c.put_resource('https://frame.test/a', '<!doctype html><title>A</title>')
            c.put_resource('https://frame.test/cancelled', '<!doctype html><title>Cancelled</title>')
            c.load_page('https://frame.test/', '<!doctype html><iframe id="f" src="/a"></iframe>')
            c.eval("globalThis.element=f;globalThis.oldWindow=f.contentWindow;f.src='/cancelled';f.remove()")
            c.advance(10)
            self.assertFalse(any(row['url'].endswith('/cancelled') for row in c.net_log()))
            c.eval("element.src='/a';document.body.appendChild(element)")
            c.advance(10)
            self.assertEqual(c.eval('[oldWindow!==element.contentWindow,element.contentDocument.title]'), [True, 'A'])

    def test_window_platform_getters_accept_the_proxy_in_each_realm(self):
        with self.context() as c:
            c.load_page('https://frame.test/', '<!doctype html><iframe></iframe>')
            self.assertEqual(c.eval('''[window,frames[0]].map(w => ({
                crypto: w.crypto instanceof w.Crypto,
                trustedTypes: w.trustedTypes instanceof w.TrustedTypePolicyFactory,
                indexedDB: w.indexedDB instanceof w.IDBFactory,
                caches: w.caches instanceof w.CacheStorage,
                cookieStore: w.cookieStore instanceof w.CookieStore,
                media: w.matchMedia('all') instanceof w.MediaQueryList,
                style: w.getComputedStyle(w.document.body) instanceof w.CSSStyleProperties,
                defaultStyle: w.getDefaultComputedStyle(w.document.body) instanceof w.CSSStyleProperties,
                performance: w.performance instanceof w.Performance,
                scheduler: w.scheduler instanceof w.Scheduler
            }))'''), [{key: True for key in ['crypto', 'trustedTypes', 'indexedDB', 'caches',
                        'cookieStore', 'media', 'style', 'defaultStyle', 'performance', 'scheduler']}] * 2)


if __name__ == '__main__':
    unittest.main()
