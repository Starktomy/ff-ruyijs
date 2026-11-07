"""Forgiving Base64 keeps binary bytes, conversion and realm error semantics."""
import base64
import itertools
import json
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class WindowEncodingTests(unittest.TestCase):
    def test_all_binary_bytes_large_ropes_and_missing_padding(self):
        data = bytes(range(256)) * 4096
        encoded = base64.b64encode(data).decode()
        with Context(shell=ROOT / "dist/js", timeout=10) as context:
            context.set("encoded", encoded)
            result = context.eval("""(() => {
                const decoded=atob(encoded),expected=Array.from({length:256},(_,i)=>String.fromCharCode(i)).join('').repeat(4096);
                const rope=encoded.slice(0,10000)+encoded.slice(10000);
                const twoByte=('\\u0100'+encoded).slice(1);
                return [decoded===expected,btoa(decoded)===encoded,atob(rope)===decoded,
                    atob(twoByte)===decoded,atob(encoded.replace(/=+$/,''))===decoded,
                    atob(' \\t\\r\\n\\f')===''];
            })()""")
            self.assertEqual(result, [True] * 6)
            sizes = (0, 1, 2, 3, 1022, 1023, 1024, 1025, 4095, 4096)
            vectors = [bytes(range(256)) * (size // 256) + bytes(range(size % 256)) for size in sizes]
            context.set("vectors", [[base64.b64encode(value).decode(), value.decode("latin1")]
                                    for value in vectors])
            self.assertTrue(context.eval("vectors.every(([encoded,raw])=>atob(encoded)===raw && btoa(raw)===encoded)"))
            context.collect_garbage()
            self.assertEqual(context.eval("atob(encoded).length"), len(data))

    def test_forgiving_decode_matches_independent_binary_reference(self):
        cases = ["".join(chars) for size in range(5) for chars in itertools.product("A/= \n", repeat=size)]
        rng = random.Random(42)
        for size in range(1, 70):
            encoded = base64.b64encode(rng.randbytes(size)).decode()
            cases.extend([encoded, encoded.rstrip("="), " \t\r\n\f".join(encoded)])
        cases += ["ab", "abc", "ab==", "abc=", "AB", "AAB", "====", "AA=A", "AA===",
                  "A", "A=", "A===", "AA\v==", "AA\u00a0==", "AA\u0100==", "AA\ud800==",
                  "AA-_", "éé==", "AA\0=="]
        expected = []
        for case in cases:
            normalized = case.translate(dict.fromkeys(map(ord, " \t\r\n\f")))
            try:
                # Python's strict decoder checks alphabet and padding; add only
                # the omitted final padding allowed by forgiving-base64.
                if len(normalized) % 4:
                    if "=" in normalized:
                        raise ValueError("partial explicit padding")
                    normalized += "=" * (-len(normalized) % 4)
                decoded = base64.b64decode(normalized, validate=True)
                expected.append([decoded.hex(), None])
            except (ValueError, UnicodeError):
                expected.append([None, "InvalidCharacterError"])
        with Context(shell=ROOT / "dist/js") as context:
            context.set("cases", cases)
            result = context.eval("""cases.map(value=>{
                try {return [Array.from(atob(value),c=>c.charCodeAt(0).toString(16).padStart(2,'0')).join(''),null]}
                catch(e){return [null,e.name]}
            })""")
            self.assertEqual(result, expected)

    def test_conversion_and_dom_errors_belong_to_the_called_realm(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://encoding.test/", "<!doctype html><iframe></iframe>")
            context.advance(10)
            result = context.eval("""(() => {
                const values=[undefined,null,123,{toString(){return 'binary\\u00ff'}}];
                const converted=values.map(x=>atob(btoa(x))===String(x));
                const frame=frames[0];let frameError=false,invalidBinary=false,symbol=false,original=false;
                try {frame.atob('A')}catch(e){frameError=e instanceof frame.DOMException && !(e instanceof DOMException) && e.name==='InvalidCharacterError'}
                try {btoa('A\\u0100')}catch(e){invalidBinary=e instanceof DOMException && e.name==='InvalidCharacterError'}
                try {atob(Symbol())}catch(e){symbol=e instanceof TypeError}
                const marker={};try {btoa({toString(){throw marker}})}catch(e){original=e===marker}
                return [...converted,frameError,invalidBinary,symbol,original];
            })()""")
            self.assertEqual(result, [True] * 8)

    def test_worker_uses_the_same_binary_decoder(self):
        with Context(shell=ROOT / "dist/js", timeout=10) as context:
            context.load_page("https://encoding.test/", "<!doctype html>")
            data = bytes(range(256))
            source = """onmessage=()=>{const bytes=atob(ENCODED);let invalid=false;
                try{atob('A')}catch(e){invalid=e instanceof DOMException && e.name==='InvalidCharacterError'}
                postMessage([btoa(bytes)===ENCODED,bytes.length,bytes.charCodeAt(255),invalid]);};""".replace("ENCODED", json.dumps(base64.b64encode(data).decode()))
            context.put_resource("https://encoding.test/worker.js", source,
                                 headers=[["Content-Type", "text/javascript"]])
            context.eval("globalThis.result=null;globalThis.worker=new Worker('/worker.js');worker.onmessage=e=>result=e.data;worker.postMessage(1)")
            for _ in range(80):
                context.advance(25)
                if context.eval("result!==null"):
                    break
            self.assertEqual(context.eval("result"), [True, 256, 255, True])


if __name__ == "__main__":
    unittest.main()
