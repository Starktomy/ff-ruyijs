"""Cached rule expansions preserve cascade order, variables and CSSOM edits."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class CascadeDeclarationTests(unittest.TestCase):
    def test_variables_are_resolved_per_element_and_edits_replace_cached_rules(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://cascade.test/", """<!doctype html><style>
                .item { display:block; margin-inline:3px 5px; padding-inline:var(--gap);
                    padding-block:7px 11px; border-inline-start:2px solid red; width:20px }
                .item { margin-left:13px }
                </style><div class="item" style="--gap:4px"></div>
                <div class="item" style="--gap:9px"></div><script>
                const sheet=document.querySelector('style').sheet;
                const nodes=[...document.querySelectorAll('.item')];
                const read=()=>nodes.map(e=>{
                    const s=getComputedStyle(e);
                    return [s.marginLeft,s.marginRight,s.paddingLeft,s.paddingRight,
                        s.paddingTop,s.paddingBottom,s.borderLeftWidth,s.borderLeftColor,
                        e.getBoundingClientRect().width];
                });
                </script>""")
            expected = [["13px", "5px", f"{gap}px", f"{gap}px", "7px", "11px", "2px",
                         "rgb(255, 0, 0)", 22 + gap * 2] for gap in (4, 9)]
            self.assertEqual(context.eval("read()"), expected)
            self.assertEqual(context.eval("read()"), expected)
            context.eval("""sheet.cssRules[0].style.setProperty('margin-inline','17px 19px','important');
                nodes[0].style.marginLeft='23px';nodes[1].style.setProperty('--gap','6px');""")
            context.collect_garbage()
            expected = [["17px", "19px", f"{gap}px", f"{gap}px", "7px", "11px", "2px",
                         "rgb(255, 0, 0)", 22 + gap * 2] for gap in (4, 6)]
            self.assertEqual(context.eval("read()"), expected)
            context.eval("sheet.cssRules[0].style.setProperty('margin-inline','17px 19px')")
            expected[0][0] = "23px"
            expected[1][0] = "13px"
            self.assertEqual(context.eval("read()"), expected)
            context.eval("sheet.deleteRule(1);sheet.insertRule('.item{margin-left:31px !important}',1)")
            for row in expected:
                row[0] = "31px"
            self.assertEqual(context.eval("read()"), expected)
            context.eval("sheet.disabled=true")
            self.assertEqual(context.eval("nodes.map(e=>getComputedStyle(e).paddingLeft)"), ["0px", "0px"])
            context.eval("sheet.disabled=false")
            self.assertEqual(context.eval("read()"), expected)


if __name__ == "__main__":
    unittest.main()
