"""Document and shadow point queries use the original composed layout."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class PointQueryTests(unittest.TestCase):
    def context(self, html):
        context = Context(shell=ROOT / "dist/js")
        self.addCleanup(context.close)
        context.configure_fingerprint({"viewport": {"width": 400, "height": 300}})
        context.load_page("https://points.test/", "<!doctype html>" + html)
        return context

    def test_overlapping_boxes_css_changes_and_pointer_exclusions(self):
        context = self.context("""<style>body{margin:0}div{position:absolute;left:20px;top:20px;
            width:100px;height:100px}#back{z-index:1}#front{z-index:2}</style>
            <div id="front"></div><div id="back"></div>""")
        self.assertEqual(context.eval("document.elementsFromPoint(30,30).map(e=>e.id||e.localName)"),
                         ["front", "back", "html"])
        context.eval("document.querySelector('#front').style.pointerEvents='none'")
        self.assertEqual(context.eval("document.elementFromPoint(30,30).id"), "back")
        context.eval("document.querySelector('#back').style.visibility='hidden'")
        self.assertEqual(context.eval("document.elementFromPoint(30,30).localName"), "html")
        context.eval("document.querySelector('#front').style.cssText='pointer-events:auto;display:none'")
        self.assertEqual(context.eval("document.elementsFromPoint(30,30).map(e=>e.localName)"), ["html"])

    def test_viewport_edges_argument_conversion_and_detached_document(self):
        context = self.context("<div></div>")
        self.assertEqual(context.eval("""(()=>{const result=[];
            for(const [x,y]of [[-1,0],[400,0],[0,300],[0,-1]]) {
                result.push(document.elementFromPoint(x,y),document.elementsFromPoint(x,y).length);
            }
            for(const call of [()=>document.elementFromPoint(),()=>document.elementFromPoint(NaN,0),
                ()=>document.elementsFromPoint(0,Infinity)]) {
                try{call();result.push(null)}catch(error){result.push(error.name)}
            }
            const detached=document.implementation.createHTMLDocument('detached');
            result.push(detached.elementFromPoint(0,0),detached.elementsFromPoint(0,0).length);
            return result})()"""), [None, 0, None, 0, None, 0, None, 0,
                                    "TypeError", "TypeError", "TypeError", None, 0])

    def test_stacking_context_keeps_descendant_z_indices_local(self):
        context = self.context("""<style>body{margin:0}#host,#front,#deep{position:absolute;
            left:0;top:0;width:100px;height:100px}#host{z-index:1}#front{z-index:2}#deep{z-index:100}
            </style><div id="host"><div id="deep"></div></div><div id="front"></div>""")
        self.assertEqual(context.eval("document.elementFromPoint(10,10).id"), "front")
        context.eval("document.querySelector('#host').style.zIndex='auto'")
        self.assertEqual(context.eval("document.elementFromPoint(10,10).id"), "deep")
        context.eval("document.querySelector('#host').style.opacity='0.5'")
        self.assertEqual(context.eval("document.elementFromPoint(10,10).id"), "front")

    def test_scroll_clipping_and_transformed_shape(self):
        context = self.context("""<style>body{margin:0}
            #clip{position:absolute;left:10px;top:10px;width:50px;height:50px;overflow:hidden}
            #child{width:120px;height:100px}
            #rotated{position:absolute;left:160px;top:60px;width:80px;height:80px;
                transform:rotate(45deg)}
            </style><div id="clip"><div id="child"></div></div><div id="rotated"></div>""")
        self.assertEqual(context.eval("[document.elementFromPoint(20,20).id,"
                                      "document.elementFromPoint(80,20).localName,"
                                      "document.elementFromPoint(200,100).id,"
                                      "document.elementFromPoint(145,45).localName]"),
                         ["child", "html", "rotated", "html"])
        context.eval("document.querySelector('#clip').scrollTop=60")
        self.assertEqual(context.eval("document.elementFromPoint(20,20).id"), "child")

    def test_closed_nested_shadow_scopes_retarget_and_deduplicate(self):
        context = self.context("""<style>body{margin:0}#host{position:absolute;left:50px;top:50px;
            width:100px;height:100px}</style><div id="host"></div>""")
        context.eval("""const host=document.querySelector('#host'),root=host.attachShadow({mode:'closed'});
            root.innerHTML='<div id="inside" style="width:80px;height:80px"><div id="nested" style="width:60px;height:60px"></div></div>';
            const nested=root.querySelector('#nested'),inner=nested.attachShadow({mode:'closed'});
            inner.innerHTML='<div id="deep" style="width:40px;height:40px"></div>';
            """)
        context.collect_garbage()
        self.assertEqual(context.eval("""({doc:document.elementFromPoint(60,60).id,
            shadow:root.elementFromPoint(60,60).id,deep:inner.elementFromPoint(60,60).id,
            allDoc:document.elementsFromPoint(60,60).map(e=>e.id||e.localName),
            allShadow:root.elementsFromPoint(60,60).map(e=>e.id),
            outside:root.elementFromPoint(10,10)})"""),
            {"doc": "host", "shadow": "nested", "deep": "deep", "allDoc": ["host", "html"],
             "allShadow": ["nested", "inside"], "outside": None})
        context.eval("root.innerHTML='text'")
        self.assertEqual(context.eval("root.elementFromPoint(55,55).id"), "host")

    def test_iframe_uses_its_own_viewport_and_receiver(self):
        context = self.context("""<iframe style="width:100px;height:80px;border:0" srcdoc=
            "<style>body{margin:0}#target{width:80px;height:60px}</style><div id='target'></div>"></iframe>""")
        context.advance(10)
        self.assertEqual(context.eval("""(()=>{const frame=document.querySelector('iframe'),doc=frame.contentDocument;
            return [doc.elementFromPoint(5,5).id,doc.elementFromPoint(110,5),
                    Document.prototype.elementFromPoint.call(doc,5,5)===doc.querySelector('#target')];})()"""),
                         ["target", None, True])
        context.eval("document.querySelector('iframe').style.display='none'")
        self.assertIsNone(context.eval("document.querySelector('iframe').contentDocument.elementFromPoint(5,5)"))


if __name__ == "__main__":
    unittest.main()
