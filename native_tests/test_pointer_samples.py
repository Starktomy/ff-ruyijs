"""Pointer sample lists follow Gecko's constructor and trusted motion behavior."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class PointerSampleTests(unittest.TestCase):
    def test_synthetic_events_and_host_click_have_no_default_samples(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://input.test/", "<!doctype html><button>click</button>")
            self.assertEqual(context.eval("""['pointermove','pointerrawupdate','click'].map(type=>{
                const e=new PointerEvent(type);document.querySelector('button').dispatchEvent(e);
                return [e.getCoalescedEvents().length,e.getPredictedEvents().length];
            })"""), [[0, 0]] * 3)
            context.eval("""window.samples=[];
                for(const type of ['pointerdown','pointerup','click'])
                    document.querySelector('button').addEventListener(type,e=>samples.push(
                        [e.getCoalescedEvents().length,e.getPredictedEvents().length]));""")
            context.click(selector="button")
            self.assertEqual(context.eval("samples"), [[0, 0]] * 3)

    def test_trusted_motion_has_independent_stable_sample(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://input.test/", "<!doctype html><button>move</button>")
            context.eval("""window.observation=null;
                document.querySelector('button').addEventListener('pointermove',e=>{
                    const first=e.getCoalescedEvents(),second=e.getCoalescedEvents(),sample=first[0];
                    first.length=0;
                    observation={length:second.length,distinctArray:first!==second,
                        distinctEvent:sample!==e,stable:sample===second[0],
                        trusted:sample.isTrusted,target:sample.target===e.target,
                        view:sample.view===window,current:sample.currentTarget,
                        phase:sample.eventPhase,bubbles:sample.bubbles,cancelable:sample.cancelable,
                        composed:sample.composed,time:sample.timeStamp===e.timeStamp,
                        coords:[sample.clientX,sample.clientY,sample.buttons,sample.pointerId],
                        nested:[sample.getCoalescedEvents().length,sample.getPredictedEvents().length],
                        predicted:e.getPredictedEvents().length};
                });""")
            context.dispatch_input("pointermove", target="document.querySelector('button')",
                                   clientX=12.5, clientY=23.25, buttons=1, pointerId=7)
            self.assertEqual(context.eval("observation"), {
                "length": 1, "distinctArray": True, "distinctEvent": True, "stable": True,
                "trusted": True, "target": True, "view": True, "current": None,
                "phase": 0, "bubbles": False, "cancelable": False, "composed": True,
                "time": True, "coords": [12.5, 23.25, 1, 7], "nested": [0, 0], "predicted": 0,
            })

    def test_trusted_pointerrawupdate_is_motion(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://input.test/", "<!doctype html><button>move</button>")
            context.eval("""window.raw=null;
                document.querySelector('button').addEventListener('pointerrawupdate',event=>{
                    raw={type:event.type,trusted:event.isTrusted,
                         sample:event.getCoalescedEvents()[0]?.clientX};
                });""")
            context.dispatch_input(
                "pointerrawupdate", target="document.querySelector('button')", clientX=17)
            self.assertEqual(context.eval("raw"), {
                "type": "pointerrawupdate", "trusted": True, "sample": 17})

    def test_constructor_copies_sequences_and_checks_pointer_brands(self):
        with Context(shell=ROOT / "dist/js") as context:
            self.assertEqual(context.eval("""(() => {
                const sample=new PointerEvent('pointermove'), list=[sample];
                const event=new PointerEvent('pointermove',{
                    coalescedEvents:list,predictedEvents:new Set(list)});
                list.length=0;
                const first=event.getCoalescedEvents();first.length=0;
                const failures=[null,{},[new MouseEvent('pointermove')],[{}]].map(value=>{
                    try {new PointerEvent('x',{coalescedEvents:value});return false;}
                    catch(e){return e instanceof TypeError;}
                });
                return [event.getCoalescedEvents()[0]===sample,
                    event.getPredictedEvents()[0]===sample,failures];
            })()"""), [True, True, [True] * 4])

    def test_foreign_receiver_keeps_sample_realm_and_return_array_realm(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://input.test/", "<iframe srcdoc='<button>move</button>'></iframe>")
            context.eval_in_frame("""window.motion=null;
                document.querySelector('button').addEventListener('pointermove',e=>motion=e);""", "0")
            context.dispatch_input("pointermove", frame="0", target="document.querySelector('button')")
            self.assertEqual(context.eval("""(() => {
                const foreign=document.querySelector('iframe').contentWindow;
                const samples=PointerEvent.prototype.getCoalescedEvents.call(foreign.motion);
                const copied=new PointerEvent('pointermove',{coalescedEvents:samples});
                return [samples instanceof Array,samples[0] instanceof foreign.PointerEvent,
                    samples[0] instanceof PointerEvent,samples[0].view===foreign,
                    copied.getCoalescedEvents()[0]===samples[0]];
            })()"""), [True, True, False, True, True])


if __name__ == "__main__":
    unittest.main()
