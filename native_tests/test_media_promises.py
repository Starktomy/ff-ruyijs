"""MediaDevices binding failures reject promises rather than escaping the call."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class MediaPromiseTests(unittest.TestCase):
    def test_invalid_receivers_reject_without_throwing(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://media.test/", "<!doctype html>")
            context.eval("""globalThis.results=[];
                for(const name of ['enumerateDevices','getUserMedia',
                                   'getDisplayMedia','selectAudioOutput']) {
                    for(const receiver of [null,undefined,0,{},MediaDevices.prototype]) {
                        try {
                            const promise=MediaDevices.prototype[name].call(receiver,{});
                            const result={name,promise:promise instanceof Promise};
                            results.push(result);
                            promise.then(()=>result.outcome='resolved',
                                error=>result.outcome=error instanceof TypeError?'TypeError':'other');
                        } catch(error) {results.push({name,threw:error.name})}
                    }
                }""")
            context.advance(1)
            results = context.eval("results")
            self.assertEqual(len(results), 20)
            for result in results:
                self.assertEqual(result, {"name": result["name"], "promise": True,
                                          "outcome": "TypeError"})

    def test_constraint_getter_failure_rejects_with_the_original_value(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://media.test/", "<!doctype html>")
            context.eval("""globalThis.results=[];
                for(const member of ['audio','video']) {
                    const reason={},constraints={};
                    Object.defineProperty(constraints,member,{get(){throw reason}});
                    try {
                        const promise=navigator.mediaDevices.getUserMedia(constraints);
                        const result={member,promise:promise instanceof Promise};
                        results.push(result);
                        promise.catch(error=>result.original=error===reason);
                    } catch(error) {results.push({member,threw:true})}
                }""")
            context.advance(1)
            self.assertEqual(context.eval("results"), [
                {"member": "audio", "promise": True, "original": True},
                {"member": "video", "promise": True, "original": True},
            ])

    def test_enumeration_and_synchronous_constraint_method(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://media.test/", "<!doctype html>")
            context.eval("""globalThis.result={};
                navigator.mediaDevices.enumerateDevices().then(devices=>{
                    result.array=Array.isArray(devices);
                    result.entries=devices.every(device=>device instanceof MediaDeviceInfo);
                });
                try {MediaDevices.prototype.getSupportedConstraints.call(null)}
                catch(error){result.synchronous=error instanceof TypeError}
                result.constraints=typeof navigator.mediaDevices.getSupportedConstraints()==='object';
                """)
            context.advance(1)
            self.assertEqual(context.eval("result"), {"array": True, "entries": True,
                             "synchronous": True, "constraints": True})


if __name__ == "__main__":
    unittest.main()
