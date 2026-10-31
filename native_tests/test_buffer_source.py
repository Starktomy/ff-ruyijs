"""Offline AudioBufferSourceNode playback uses the supplied samples and schedule."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class BufferSourceTests(unittest.TestCase):
    def render(self, code, before_render=None):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://audio.test/", "<!doctype html>")
            context.eval(code)
            if before_render:
                context.collect_garbage()
                context.eval(before_render)
            context.advance(10)
            return context.eval("result")

    def test_constant_samples_reach_promise_and_completion_event(self):
        self.assertEqual(self.render("""const result={},ctx=new OfflineAudioContext(1,1000,44100);
            const buffer=ctx.createBuffer(1,1000,44100);buffer.getChannelData(0).fill(0.5);
            const source=ctx.createBufferSource();source.buffer=buffer;source.connect(ctx.destination);
            source.start();ctx.oncomplete=event=>result.event=[...new Set(event.renderedBuffer.getChannelData(0))];
            ctx.startRendering().then(buffer=>result.promise=[...new Set(buffer.getChannelData(0))]);
            """), {"promise": [0.5], "event": [0.5]})

    def test_constructor_stereo_gain_and_gc(self):
        self.assertEqual(self.render("""const result={},ctx=new OfflineAudioContext(2,4,8000);
            const buffer=ctx.createBuffer(2,4,8000);
            buffer.getChannelData(0).set([1,2,3,4]);buffer.getChannelData(1).set([-1,-2,-3,-4]);
            const source=new AudioBufferSourceNode(ctx,{buffer}),gain=ctx.createGain();gain.gain.value=0.5;
            source.connect(gain);gain.connect(ctx.destination);source.start();""",
            """ctx.startRendering().then(buffer=>{result.left=[...buffer.getChannelData(0)];
                result.right=[...buffer.getChannelData(1)]});"""),
            {"left": [0.5, 1, 1.5, 2], "right": [-0.5, -1, -1.5, -2]})

    def test_start_offset_duration_and_stop(self):
        for action, expected in [
            ("source.start(2/8000,1/8000,3/8000)", [0, 0, 2, 3, 4, 0, 0, 0]),
            ("source.start();source.stop(4/8000)", [1, 2, 3, 4, 0, 0, 0, 0]),
        ]:
            with self.subTest(action=action):
                self.assertEqual(self.render("""const result={},ctx=new OfflineAudioContext(1,8,8000);
                    const buffer=ctx.createBuffer(1,8,8000);buffer.getChannelData(0).set([1,2,3,4,5,6,7,8]);
                    const source=ctx.createBufferSource();source.buffer=buffer;source.connect(ctx.destination);
                    """ + action + ";ctx.startRendering().then(buffer=>result.samples=[...buffer.getChannelData(0)]);"),
                    {"samples": expected})

    def test_loop_wraps_to_the_configured_region(self):
        self.assertEqual(self.render("""const result={},ctx=new OfflineAudioContext(1,8,8000);
            const buffer=ctx.createBuffer(1,4,8000);buffer.getChannelData(0).set([1,2,3,4]);
            const source=ctx.createBufferSource();source.buffer=buffer;source.loop=true;
            source.loopStart=1/8000;source.loopEnd=3/8000;source.connect(ctx.destination);source.start();
            ctx.startRendering().then(buffer=>result.samples=[...buffer.getChannelData(0)]);"""),
            {"samples": [1, 2, 3, 2, 3, 2, 3, 2]})

    def test_unstarted_and_disconnected_sources_are_silent(self):
        self.assertEqual(self.render("""const result={},ctx=new OfflineAudioContext(1,8,8000);
            const buffer=ctx.createBuffer(1,8,8000);buffer.getChannelData(0).fill(0.5);
            const unstarted=ctx.createBufferSource();unstarted.buffer=buffer;unstarted.connect(ctx.destination);
            const disconnected=ctx.createBufferSource();disconnected.buffer=buffer;disconnected.start();
            const empty=ctx.createBufferSource();empty.connect(ctx.destination);empty.start();
            ctx.startRendering().then(buffer=>result.samples=[...new Set(buffer.getChannelData(0))]);"""),
            {"samples": [0]})

    def test_source_schedule_validation_preserves_start_state(self):
        self.assertEqual(self.render("""const result={errors:[]},ctx=new OfflineAudioContext(1,8,8000);
            const source=ctx.createBufferSource();
            for(const call of [()=>source.stop(),()=>source.start(-1),()=>source.start(0,-1),
                ()=>source.start(0,0,-1),()=>source.start(Infinity),()=>source.start(),()=>source.start()]) {
                try{call();result.errors.push(null)}catch(error){result.errors.push(error.name)}
            }"""), {"errors": ["InvalidStateError", "RangeError", "RangeError", "RangeError",
                               "TypeError", None, "InvalidStateError"]})


if __name__ == "__main__":
    unittest.main()
