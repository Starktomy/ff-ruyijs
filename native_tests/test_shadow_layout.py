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

    def test_inline_reuse_tracks_inheritance_variables_and_has(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://layout.test/", """<!doctype html><div id="host"></div><script>
                const host=document.getElementById('host'), root=host.attachShadow({mode:'closed'});
                root.innerHTML='<style>.parent{display:block;font-size:10px;--w:20px}'+
                    '.leaf{display:block;width:var(--w);height:1em}'+
                    '.parent:has(.trigger[style]) .leaf{width:55px}'+
                    '.trigger[style] + .tail{width:65px}.tail{display:block;width:15px}</style>'+
                    '<section class="parent"><div class="leaf"></div><i class="trigger"></i>'+
                    '<div class="tail"></div></section>';
                const parent=root.querySelector('.parent'), leaf=root.querySelector('.leaf');
                const trigger=root.querySelector('.trigger'), tail=root.querySelector('.tail');
                const read=()=>[leaf.getBoundingClientRect().width,leaf.getBoundingClientRect().height,
                    tail.getBoundingClientRect().width];
                </script>""")
            self.assertEqual(context.eval("[read(),read()]"), [[20, 10, 15]] * 2)
            context.eval("parent.style.setProperty('--w','35px')")
            self.assertEqual(context.eval("read()"), [35, 10, 15])
            context.eval("parent.style.fontSize='20px'")
            self.assertEqual(context.eval("read()"), [35, 20, 15])
            context.eval("trigger.style.color='red'")
            self.assertEqual(context.eval("read()"), [55, 20, 65])
            context.eval("trigger.removeAttribute('style')")
            context.collect_garbage()
            self.assertEqual(context.eval("read()"), [35, 20, 15])
            context.eval("trigger.setAttribute('style','')")
            self.assertEqual(context.eval("read()"), [55, 20, 65])
            context.eval("trigger.removeAttribute('style')")
            self.assertEqual(context.eval("read()"), [35, 20, 15])

    def test_inline_reuse_rediscovers_revealed_shadow_scopes(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://layout.test/", """<!doctype html><div id="host"></div><script>
                const root=document.getElementById('host').attachShadow({mode:'closed'});
                root.innerHTML='<style>.leaf{display:block;width:20px;height:10px}</style>'+
                    '<div class="leaf"></div><section style="display:none"></section>';
                const leaf=root.querySelector('.leaf'), hidden=root.querySelector('section');
                const nested=hidden.attachShadow({mode:'closed'});
                nested.innerHTML='<style>div{display:block;width:30px;height:10px}</style><div></div>';
                const probe=nested.querySelector('div'), rule=nested.querySelector('style').sheet.cssRules[0];
                const read=()=>[leaf.getBoundingClientRect().width,probe.getBoundingClientRect().width];
                </script>""")
            self.assertEqual(context.eval("[read(),read()]"), [[20, 0]] * 2)
            context.eval("hidden.style.display='block'")
            self.assertEqual(context.eval("read()"), [20, 30])
            context.eval("leaf.style.width='25px';read();rule.style.width='45px'")
            self.assertEqual(context.eval("read()"), [25, 45])
            context.eval("hidden.style.display='none'")
            self.assertEqual(context.eval("read()"), [25, 0])
            context.eval("rule.style.width='60px';hidden.style.display='block'")
            context.collect_garbage()
            self.assertEqual(context.eval("read()"), [25, 60])

    def test_structure_changes_keep_scope_specific_styles(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://layout.test/", """<!doctype html><div id="a"></div><div id="b"></div><script>
                const roots=['a','b'].map(id=>document.getElementById(id).attachShadow({mode:'closed'}));
                roots.forEach((root,i)=>root.innerHTML='<style>.leaf{display:block;width:'+
                    (20+10*i)+'px;height:10px}</style><div class="leaf"></div>');
                const probe=roots[0].querySelector('.leaf');
                const read=()=>probe.getBoundingClientRect().width;
                </script>""")
            self.assertEqual(context.eval("[read(),read()]"), [20, 20])
            context.eval("roots[1].appendChild(probe)")
            self.assertEqual(context.eval("read()"), 30)
            context.eval("probe.style.height='15px'")
            self.assertEqual(context.eval("read()"), 30)
            context.eval("roots[0].appendChild(probe)")
            self.assertEqual(context.eval("read()"), 20)
            context.eval("probe.className='other';probe.style.width='40px'")
            self.assertEqual(context.eval("read()"), 40)
            context.eval("probe.style.width='';probe.className='leaf'")
            context.collect_garbage()
            self.assertEqual(context.eval("read()"), 20)


if __name__ == "__main__":
    unittest.main()
