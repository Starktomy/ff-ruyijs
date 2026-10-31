"""Composed layout reuse must observe every shadow stylesheet's mutations."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class ShadowLayoutTests(unittest.TestCase):
    def test_nested_closed_scopes_cssom_and_adopted_sheets(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://layout.test/", """<!doctype html>
                <div id="host"></div><script>
                const host=document.getElementById('host');
                const outer=host.attachShadow({mode:'closed'});
                outer.innerHTML='<style>div{display:block;width:100px}</style><div></div>';
                const inner=outer.querySelector('div').attachShadow({mode:'closed'});
                inner.innerHTML='<style>#probe{display:block;width:30px;height:10px}</style><div id="probe"></div>';
                const probe=inner.querySelector('#probe');
                const sheet=inner.querySelector('style').sheet;
                const width=()=>probe.getBoundingClientRect().width;
                </script>""")
            self.assertEqual(context.eval("[width(),width(),width()]"), [30, 30, 30])
            context.eval("sheet.cssRules[0].style.width='55px'")
            self.assertEqual(context.eval("[width(),width()]"), [55, 55])
            # A DOM change triggers another layout. Its reused cache must still
            # track the nested scope when the next change is CSSOM-only.
            context.eval("host.style.padding='2px';width();sheet.cssRules[0].style.width='75px'")
            self.assertEqual(context.eval("width()"), 75)
            context.eval("""const adopted=new CSSStyleSheet();
                adopted.replaceSync('#probe{width:90px}');inner.adoptedStyleSheets=[adopted];""")
            self.assertEqual(context.eval("width()"), 90)
            context.eval("adopted.replaceSync('#probe{width:110px}')")
            context.collect_garbage()
            self.assertEqual(context.eval("[width(),width()]"), [110, 110])
            context.eval("adopted.disabled=true")
            self.assertEqual(context.eval("width()"), 75)

    def test_shadow_sheet_updates_frame_viewport_after_dom_changes(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://layout.test/", """<!doctype html>
                <div id="host"></div><script>
                const host=document.getElementById('host');
                const root=host.attachShadow({mode:'closed'});
                root.innerHTML='<style>iframe{display:block;width:300px;height:65px;border:0}</style><iframe></iframe>';
                const frame=root.querySelector('iframe');
                const rule=root.querySelector('style').sheet.cssRules[0];
                const size=()=>[frame.contentWindow.innerWidth,frame.contentWindow.innerHeight];
                </script>""")
            self.assertEqual(context.eval("[size(),size()]"), [[300, 65], [300, 65]])
            context.eval("rule.style.width='340px'")
            self.assertEqual(context.eval("size()"), [340, 65])
            context.eval("document.body.appendChild(document.createElement('p'));size();rule.style.height='90px'")
            context.collect_garbage()
            self.assertEqual(context.eval("[size(),size()]"), [[340, 90], [340, 90]])
            context.eval("host.remove();document.body.getBoundingClientRect();document.body.appendChild(host)")
            # Reconnecting the style element creates its sheet from source
            # again. Firefox 159 also drops the old CSSOM-only edits here.
            self.assertEqual(context.eval("size()"), [300, 65])


if __name__ == "__main__":
    unittest.main()
