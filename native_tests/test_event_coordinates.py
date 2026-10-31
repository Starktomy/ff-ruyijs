"""Mouse coordinates use the document scroll and the target padding frame."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class EventCoordinateTests(unittest.TestCase):
    def test_click_uses_padding_edge_without_script_geometry(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://input.test/", """<!doctype html><div id="target"
                style="position:absolute;left:100px;top:60px;width:60px;height:40px;
                border:2px solid;padding:0"></div>""")
            context.eval("""window.points=[]; const target=document.getElementById('target');
                target.getBoundingClientRect=()=>{throw Error('script geometry called');};
                target.addEventListener('click',e=>points.push(
                    [e.clientX,e.clientY,e.offsetX,e.offsetY,e.pageX,e.pageY]));""")
            context.click(selector="#target")
            self.assertEqual(context.eval("points"), [[132, 82, 30, 20, 132, 82]])

    def test_transformed_pointer_uses_local_padding_coordinates(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://input.test/", """<!doctype html><div id="target"
                style="position:absolute;left:100px;top:80px;width:40px;height:20px;
                border:2px solid;padding:4px;transform:scale(2);transform-origin:0 0"></div>""")
            context.eval("""window.point=null;
                document.getElementById('target').addEventListener('pointermove',e=>
                    point=[e.offsetX,e.offsetY]);""")
            context.dispatch_input("pointermove", target="document.getElementById('target')",
                                   clientX=152.5, clientY=112.5)
            self.assertEqual(context.eval("point"), [24.25, 14.25])
            context.eval("document.getElementById('target').style.transform='scale(0)'")
            context.dispatch_input("pointermove", target="document.getElementById('target')",
                                   clientX=152, clientY=112)
            self.assertEqual(context.eval("point"), [0, 0])

    def test_scroll_uses_event_document_in_iframe(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://input.test/", """<!doctype html><iframe style="width:300px;height:200px"
                srcdoc="<!doctype html><body style='margin:0;height:2000px'>
                <div id='target' style='position:absolute;left:30px;top:600px;
                width:40px;height:20px;border:2px solid'></div>"></iframe>""")
            context.eval_in_frame("""scrollTo(0,500);window.points=[];
                document.getElementById('target').addEventListener('click',e=>points.push(
                    [e.clientX,e.clientY,e.pageX,e.pageY,e.offsetX,e.offsetY]));""", "0")
            context.click(frame="0", selector="#target")
            self.assertEqual(context.eval_in_frame("points", "0"), [[52, 112, 52, 612, 20, 10]])
            self.assertEqual(context.eval("scrollY"), 0)

    def test_offsets_follow_shadow_retargeting(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://input.test/", """<!doctype html><div id="host"
                style="position:absolute;left:40px;top:30px;width:120px;height:100px"></div>""")
            context.eval("""window.points=[];const host=document.getElementById('host');
                const root=host.attachShadow({mode:'closed'});
                root.innerHTML='<div id="target" style="position:absolute;left:10px;top:20px;'+
                    'width:30px;height:20px;border:2px solid"></div>';
                root.firstChild.addEventListener('click',e=>points.push(['inner',e.offsetX,e.offsetY]));
                host.addEventListener('click',e=>points.push(['host',e.offsetX,e.offsetY]));""")
            context.click(selector="#target")
            self.assertEqual(context.eval("points"), [["inner", 15, 10], ["host", 27, 32]])

    def test_undispatched_and_non_element_targets(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://input.test/", "<!doctype html><body></body>")
            result = context.eval("""(() => {
                const event=new MouseEvent('probe',{clientX:12,clientY:23});
                const before=[event.offsetX,event.offsetY];
                window.dispatchEvent(event);
                return [before,[event.offsetX,event.offsetY]];
            })()""")
            self.assertEqual(result, [[12, 23], [0, 0]])


if __name__ == "__main__":
    unittest.main()
