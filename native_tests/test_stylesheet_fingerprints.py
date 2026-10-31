"""Stylesheet summaries must invalidate through every live CSSOM mutation path."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class StylesheetFingerprintTests(unittest.TestCase):
    def width(self, context, expected):
        # Warm both the computed cascade and layout caches, then read again.
        for _ in range(2):
            self.assertEqual(context.eval("[getComputedStyle(probe).width,"
                                          "probe.getBoundingClientRect().width]"),
                             [f"{expected}px", expected])

    def test_nested_declarations_selectors_and_rule_lists(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://fingerprint.test/", """<!doctype html><style>
                div { display:block; width:10px }
                @media all { @supports (display:block) { .probe { width:20px } } }
                </style><div id="probe" class="probe"></div><script>
                const probe=document.getElementById('probe'), sheet=document.styleSheets[0];
                const group=sheet.cssRules[1].cssRules[0], rule=group.cssRules[0];
                </script>""")
            self.width(context, 20)
            edits = [
                ("rule.style.width='25px'", 25),
                ("rule.style.setProperty('width','30px','important')", 30),
                ("rule.style.removeProperty('width')", 10),
                ("rule.style.cssText='width:35px'", 35),
                ("rule.style='width:40px'", 40),
                ("rule.selectorText='.other'", 10),
                ("rule.selectorText='.probe'", 40),
                ("group.insertRule('.probe{width:45px}',1)", 45),
                ("group.deleteRule(1)", 40),
                ("group.deleteRule(0)", 10),
                ("rule.style.width='99px';group.insertRule('.probe{width:50px}',0)", 50),
                ("sheet.insertRule('.probe{width:55px}',2)", 55),
                ("sheet.deleteRule(2)", 50),
            ]
            for script, expected in edits:
                with self.subTest(script=script):
                    context.eval(script)
                    self.width(context, expected)
            context.collect_garbage()
            self.width(context, 50)

    def test_media_mutations_and_environment_remain_live(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://fingerprint.test/", """<!doctype html>
                <iframe style="width:400px;height:300px;border:0"></iframe><script>
                const frame=document.querySelector('iframe'), doc=frame.contentDocument;
                doc.head.innerHTML='<style>div{display:block;width:10px}</style>'+
                    '<style>@media (min-width:500px){.probe{width:20px}}</style>';
                doc.body.innerHTML='<div id="probe" class="probe"></div>';
                const probe=doc.getElementById('probe'), sheet=doc.styleSheets[1];
                const media=sheet.cssRules[0], rule=media.cssRules[0];
                </script>""")
            self.width(context, 10)
            context.eval("frame.style.width='600px'")
            self.width(context, 20)
            edits = [
                ("media.media.mediaText='not all'", 10),
                ("media.media.appendMedium('all')", 20),
                ("media.media.deleteMedium('all')", 10),
                ("media.media='all'", 20),
                ("sheet.media='not all'", 10),
                ("sheet.media.mediaText='all'", 20),
                ("sheet.disabled=true", 10),
                ("rule.style.width='30px'", 10),
                ("sheet.disabled=false", 30),
                ("media.media='(min-width:700px)'", 10),
            ]
            for script, expected in edits:
                with self.subTest(script=script):
                    context.eval(script)
                    self.width(context, expected)
            context.eval("frame.style.width='800px'")
            self.width(context, 30)

    def test_replacement_adoption_order_and_retired_rules(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://fingerprint.test/", """<!doctype html>
                <style>div{display:block;width:10px}</style><div id="probe"></div><script>
                const probe=document.getElementById('probe'), source=document.querySelector('style');
                const retired=source.sheet.cssRules[0];
                const first=new CSSStyleSheet(), second=new CSSStyleSheet();
                first.replaceSync('div{width:20px}'); second.replaceSync('div{width:30px}');
                </script>""")
            self.width(context, 10)
            edits = [
                ("source.textContent='div{display:block;width:15px}'", 15),
                ("retired.style.width='99px'", 15),
                ("document.adoptedStyleSheets=[first,second]", 30),
                ("document.adoptedStyleSheets=[second,first]", 20),
                ("globalThis.old=first.cssRules[0];first.replaceSync('div{width:40px}')", 40),
                ("old.style.width='88px'", 40),
                ("first.deleteRule(0)", 30),
                ("first.insertRule('@media all {div{width:45px}}',0)", 45),
                ("first.cssRules[0].cssRules[0].style.width='50px'", 50),
            ]
            for script, expected in edits:
                with self.subTest(script=script):
                    context.eval(script)
                    self.width(context, expected)
            context.eval("globalThis.done=false;first.replace('div{width:60px}').then(()=>done=true)")
            context.advance(10)
            self.assertTrue(context.eval("done"))
            context.collect_garbage()
            self.width(context, 60)

    def test_shared_sheet_in_closed_scopes_and_cross_realm_edits(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://fingerprint.test/", """<!doctype html>
                <div id="a"></div><div id="b"></div><iframe></iframe><script>
                const shared=new CSSStyleSheet();
                shared.replaceSync('@media all {div{display:block;width:20px}}');
                const roots=['a','b'].map(id=>document.getElementById(id).attachShadow({mode:'closed'}));
                for(const root of roots){root.innerHTML='<div></div>';root.adoptedStyleSheets=[shared]}
                const nodes=roots.map(root=>root.firstChild);
                const read=()=>nodes.map(e=>[getComputedStyle(e).width,e.getBoundingClientRect().width]);
                </script>""")
            self.assertEqual(context.eval("read()"), [["20px", 20]] * 2)
            context.eval("shared.cssRules[0].cssRules[0].style.width='35px'")
            self.assertEqual(context.eval("read()"), [["35px", 35]] * 2)
            context.eval("""const frame=document.querySelector('iframe').contentWindow;
                frame.document.head.innerHTML='<style>div{display:block;width:25px}</style>';
                frame.document.body.innerHTML='<div></div>';
                const foreign=frame.document.body.firstChild, rule=frame.document.styleSheets[0].cssRules[0];
                const foreignRead=()=>[frame.getComputedStyle(foreign).width,foreign.getBoundingClientRect().width];
                """)
            self.assertEqual(context.eval("foreignRead()"), ["25px", 25])
            context.eval("rule.style.cssText='display:block;width:45px'")
            context.collect_garbage()
            self.assertEqual(context.eval("foreignRead()"), ["45px", 45])


if __name__ == "__main__":
    unittest.main()
