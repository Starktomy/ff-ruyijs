"""WebIDL receiver failures retain Firefox's interface and member text."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


SOURCE = r"""
const out={};
const fragment=document.createDocumentFragment();
const probes=[
  ['createElement',Document.prototype.createElement,null],
  ['attachShadow',Element.prototype.attachShadow,null],
  ['setAttribute',Element.prototype.setAttribute,null],
  ['querySelector',Element.prototype.querySelector,null],
  ['fragmentQuery',fragment.querySelector,null],
];
for(const [name,fn,receiver] of probes){
  try{Reflect.apply(fn,receiver,[]);out[name]='accepted'}
  catch(e){out[name]=e.name+': '+e.message}
}
try{Reflect.apply(EventTarget.prototype.addEventListener,null,[])}
catch(e){out.addEventListener=e.name+': '+e.message}
return out;
"""


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class ReceiverErrorTests(unittest.TestCase):
    def test_brand_and_argument_errors_match_firefox159(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://receiver.test/", "<!doctype html><body>")
            actual = context.eval("(() => {" + SOURCE + "})()")
        self.assertEqual(actual, {
            "createElement": "TypeError: 'createElement' called on an object that does not implement interface Document.",
            "attachShadow": "TypeError: 'attachShadow' called on an object that does not implement interface Element.",
            "setAttribute": "TypeError: 'setAttribute' called on an object that does not implement interface Element.",
            "querySelector": "TypeError: 'querySelector' called on an object that does not implement interface Element.",
            "fragmentQuery": "TypeError: 'querySelector' called on an object that does not implement interface DocumentFragment.",
            "addEventListener": "TypeError: EventTarget.addEventListener: At least 2 arguments required, but only 0 passed",
        })


if __name__ == "__main__":
    unittest.main()
