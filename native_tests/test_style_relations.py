"""Transient selector relations follow mutations and keep their original realm."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class StyleRelationTests(unittest.TestCase):
    def test_siblings_and_has_follow_moves_removals_and_new_children(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://relations.test/", """<!doctype html><style>
                .row > i { display:block; width:29px; height:5px }
                .row > i:nth-child(odd) { width:43px }
                .row > i:first-child { width:71px }
                .row > i:last-child { width:83px }
                .row > i:only-child { width:97px }
                .row > i:has(+ .hot) { height:13px }
                .row > .hot ~ i { height:17px }
                </style><div class="row"></div><script>
                const row=document.querySelector('.row');
                for(let i=0;i<160;i++) row.appendChild(document.createElement('i'));
                const read=()=>[...row.children].map(e=>{
                    const r=e.getBoundingClientRect();return [r.width,r.height];
                });
                </script>""")
            expected = [[71 if i == 0 else 83 if i == 159 else 43 if i % 2 == 0 else 29, 5]
                        for i in range(160)]
            self.assertEqual(context.eval("read()"), expected)
            context.eval("row.children[80].className='hot'")
            expected[79][1] = 13
            for i in range(81, 160):
                expected[i][1] = 17
            self.assertEqual(context.eval("read()"), expected)
            context.eval("row.prepend(row.children[80]);row.lastElementChild.remove()")
            context.collect_garbage()
            expected = [[71 if i == 0 else 83 if i == 158 else 43 if i % 2 == 0 else 29,
                         5 if i == 0 else 17] for i in range(159)]
            self.assertEqual(context.eval("read()"), expected)
            context.eval("while(row.children.length>1)row.lastElementChild.remove()")
            self.assertEqual(context.eval("read()"), [[97, 5]])
            context.eval("row.appendChild(document.createElement('i'))")
            self.assertEqual(context.eval("read()"), [[71, 5], [83, 17]])

    def test_default_style_copy_and_cross_realm_adoption(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://relations.test/", """<!doctype html>
                <style>.parent > span{display:block;width:41px}</style>
                <div class="parent"><span id="probe"></span></div><iframe></iframe>""")
            context.advance(1)
            self.assertEqual(context.eval("""const probe=document.querySelector('#probe');
                const style=getComputedStyle(probe);
                [style.width,getDefaultComputedStyle(probe).display]"""), ["41px", "inline"])
            context.eval("""frames[0].document.body.innerHTML=
                '<style>.other > span{display:block;width:63px}</style><div class="other"></div>';
                frames[0].document.querySelector('.other').appendChild(probe);""")
            context.collect_garbage()
            self.assertEqual(context.eval("""[style.width,probe.getBoundingClientRect().width,
                frames[0].getDefaultComputedStyle(probe).display]"""), ["63px", 63, "inline"])
            context.eval("document.querySelector('.parent').appendChild(probe)")
            self.assertEqual(context.eval("[style.width,probe.getBoundingClientRect().width]"), ["41px", 41])


if __name__ == "__main__":
    unittest.main()
