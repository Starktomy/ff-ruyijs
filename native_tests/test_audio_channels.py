"""AudioBuffer channel copies are bounded, overlap safe Float32Array operations."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class AudioChannelTests(unittest.TestCase):
    def context(self):
        context = Context(shell=ROOT / "dist/js")
        self.addCleanup(context.close)
        context.load_page("https://audio.test/", "<!doctype html>")
        context.eval("""const buffer=new AudioContext().createBuffer(1,5,44100);
            const channel=buffer.getChannelData(0);channel.set([1,2,3,4,5]);""")
        return context

    def test_copies_stop_at_both_array_bounds_and_preserve_the_suffix(self):
        context = self.context()
        self.assertEqual(context.eval("""(()=>{
            const short=new Float32Array(3);buffer.copyFromChannel(short,0,1);
            const long=new Float32Array(8).fill(7);buffer.copyFromChannel(long,0,3);
            buffer.copyToChannel(new Float32Array([9,8,7,6]),0,3);
            const unchanged=[...channel];
            buffer.copyToChannel(new Float32Array([0]),0,5);
            buffer.copyFromChannel(long,0,-1);
            return {short:[...short],long:[...long],unchanged,channel:[...channel]};
        })()"""), {"short": [2, 3, 4], "long": [4, 5, 7, 7, 7, 7, 7, 7],
                   "unchanged": [1, 2, 3, 9, 8], "channel": [1, 2, 3, 9, 8]})

    def test_overlapping_views_copy_the_original_samples(self):
        context = self.context()
        self.assertEqual(context.eval("""(()=>{
            buffer.copyToChannel(channel.subarray(0,4),0,1);
            const to=[...channel];channel.set([1,2,3,4,5]);
            buffer.copyFromChannel(channel.subarray(1,4),0);
            const from=[...channel];
            const external=new Float32Array([9,8,7,6,5]);
            buffer.copyToChannel(external.subarray(1,3),0,2);
            return {to,from,view:[...channel]};
        })()"""), {"to": [1, 1, 2, 3, 4], "from": [1, 1, 2, 3, 5],
                   "view": [1, 1, 8, 7, 5]})

    def test_webidl_arguments_unsigned_indices_and_detached_arrays(self):
        context = self.context()
        self.assertEqual(context.eval("""(()=>{
            const errors=[];
            for(const call of [()=>buffer.getChannelData(),()=>buffer.getChannelData(-1),
                ()=>buffer.copyFromChannel([],0),()=>buffer.copyToChannel(new Float64Array(2),0),
                ()=>buffer.copyFromChannel(new Float32Array(2)),
                ()=>buffer.copyFromChannel(new Float32Array(2),1)]) {
                try{call();errors.push(null)}catch(error){errors.push(error.name)}
            }
            const data=new Float32Array(2);
            buffer.copyFromChannel(data,NaN,2**32+1);
            const wrapped=[...data];
            data.buffer.transfer();buffer.copyFromChannel(data,0);buffer.copyToChannel(data,0);
            return {errors,wrapped,same:buffer.getChannelData(Infinity)===channel,
                    channel:[...channel]};
        })()"""), {"errors": ["TypeError", "IndexSizeError", "TypeError", "TypeError",
                               "TypeError", "IndexSizeError"], "wrapped": [2, 3],
                   "same": True, "channel": [1, 2, 3, 4, 5]})


if __name__ == "__main__":
    unittest.main()
