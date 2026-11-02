"""XHR Blob responses use native bytes, MIME and realm-local factories."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class XhrBlobTests(unittest.TestCase):
    def test_blob_is_cached_binary_exact_and_uses_original_constructor(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://xhr.test/", "<!doctype html>")
            context.put_resource("https://xhr.test/bytes", b"\x00\xffA\xc3\xa9", headers=[
                ["Content-Type", "Application/Octet-Stream; charset=binary"]])
            context.eval("""globalThis.result=null;const OriginalBlob=Blob;
                globalThis.Blob=function(){throw new Error('public constructor called')};
                const xhr=new XMLHttpRequest();xhr.open('GET','/bytes');xhr.responseType='blob';
                globalThis.before=xhr.response;
                xhr.onload=async()=>{const b=xhr.response;
                    result=b===null?{missing:true}:{blob:b instanceof OriginalBlob,
                        same:b===xhr.response,size:b.size,type:b.type,
                        bytes:[...new Uint8Array(await b.arrayBuffer())]};};xhr.send();""")
            for _ in range(20):
                context.advance(10)
                result = context.eval("result")
                if result is not None:
                    break
            self.assertIsNone(context.eval("before"))
            self.assertEqual(result, {"blob": True, "same": True, "size": 5,
                                     "type": "application/octet-stream", "bytes": [0, 255, 65, 195, 169]})

    def test_override_error_body_and_reopen_replace_the_cached_blob(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://xhr.test/", "<!doctype html>")
            context.put_resource("https://xhr.test/error", '{"error":"DENIED ACCESS"}', status=400,
                                 headers=[["Content-Type", "text/plain; charset=utf-8"]])
            context.put_resource("https://xhr.test/empty", b"", status=204)
            context.eval("""globalThis.result=null;const xhr=new XMLHttpRequest();
                xhr.open('GET','/error');xhr.responseType='blob';xhr.overrideMimeType('Application/JSON');
                xhr.onload=async()=>{const first=xhr.response;
                    if(!first){result={missing:true};return}
                    const error={status:xhr.status,type:first.type,body:await first.text()};
                    xhr.open('GET','/empty');const reset=xhr.response;
                    xhr.onload=()=>{const second=xhr.response;
                        result={error,reset,empty:second instanceof Blob,size:second?.size,
                            type:second?.type,different:first!==second};};xhr.send();};xhr.send();""")
            for _ in range(30):
                context.advance(10)
                result = context.eval("result")
                if result is not None:
                    break
            self.assertEqual(result, {"error": {"status": 400, "type": "application/json",
                                               "body": '{"error":"DENIED ACCESS"}'},
                                      "reset": None, "empty": True, "size": 0, "type": "", "different": True})

    def test_borrowed_getter_preserves_the_xhr_realm_and_abort_clears_result(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://xhr.test/", "<!doctype html><iframe></iframe>")
            context.put_resource("https://xhr.test/blob", "child bytes",
                                 headers=[["Content-Type", "text/plain"]])
            context.eval("""globalThis.result=null;globalThis.child=frames[0];
                globalThis.xhr=new child.XMLHttpRequest();xhr.open('GET','https://xhr.test/blob');
                xhr.responseType='blob';const getter=Object.getOwnPropertyDescriptor(
                    XMLHttpRequest.prototype,'response').get;
                xhr.onload=async()=>{const b=getter.call(xhr);
                    if(!b){result={missing:true};return}
                    result={child:b instanceof child.Blob,parent:b instanceof Blob,
                        ownPrototype:Object.getPrototypeOf(b)===child.Blob.prototype,
                        same:b===xhr.response,text:await b.text()};};xhr.send();""")
            for _ in range(20):
                context.advance(10)
                result = context.eval("result")
                if result is not None:
                    break
            context.collect_garbage()
            self.assertEqual(result, {"child": True, "parent": False, "ownPrototype": True,
                                      "same": True, "text": "child bytes"})
            self.assertEqual(context.eval("xhr.open('GET','https://xhr.test/blob');"
                                          "xhr.send();xhr.abort();[xhr.status,xhr.response]"),
                             [0, None])


if __name__ == "__main__":
    unittest.main()
