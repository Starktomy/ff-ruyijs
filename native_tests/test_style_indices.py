"""CSSOM declaration indices expose live enumerable property names."""
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context, UNDEFINED


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class StyleIndexTests(unittest.TestCase):
    def test_computed_indices_match_firefox159_and_are_read_only(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://style.test/", "<!doctype html><body></body>")
            encoded = context.eval("globalThis.s=getComputedStyle(document.body);JSON.stringify(s)")
            # Captured independently from Firefox 159's enabled longhand enumeration.
            self.assertEqual(hashlib.sha256(encoded.encode()).hexdigest(),
                             "337715a34605ee5a961ddf597ba26470c9bb278a491b6ae635edaf0139943918")
            self.assertEqual(context.eval("""[s.length,s[0],s.item(0),s[s.length],s.item(s.length),
                Array.from(s).length,Object.keys(s).length,s instanceof CSSStyleDeclaration,
                Reflect.set(s,'0','changed'),Reflect.deleteProperty(s,'0'),
                Reflect.defineProperty(s,'0',{value:'changed'}),
                Reflect.deleteProperty(s,'4294967294'),s.cssText]"""),
                             [393, "accent-color", "accent-color", UNDEFINED, "", 393, 393, True,
                              False, False, False, True, ""])
            self.assertEqual(context.eval("Object.getOwnPropertyDescriptor(s,'0')"),
                             {"value": "accent-color", "writable": False,
                              "enumerable": True, "configurable": True})

    def test_custom_indices_track_cascade_detach_and_reinsert(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://style.test/", "<!doctype html><style>body{--parent:yes}</style><div></div>")
            context.eval("globalThis.e=document.querySelector('div');globalThis.s=getComputedStyle(e)")
            self.assertEqual(context.eval("[s.length,s[s.length-1]]"), [394, "--parent"])
            context.eval("e.style.setProperty('--extra','one')")
            self.assertEqual(context.eval("[s.length,Array.from(s).slice(393).sort()]"),
                             [395, ["--extra", "--parent"]])
            context.eval("e.remove()")
            context.collect_garbage()
            self.assertEqual(context.eval("[s.length,s[0],s.item(0),Object.keys(s),JSON.stringify(s)]"),
                             [0, UNDEFINED, "", [], "{}"])
            context.eval("document.body.appendChild(e);e.style.removeProperty('--extra')")
            self.assertEqual(context.eval("[s.length,s[393],s.item(393),s.getPropertyValue('--parent')]"),
                             [394, "--parent", "--parent", "yes"])

    def test_rule_indices_are_live_and_preserve_expandos(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://style.test/", "<!doctype html><style>div{color:red;width:10px}</style>")
            context.eval("globalThis.s=document.styleSheets[0].cssRules[0].style")
            self.assertEqual(context.eval("[s[0],s[1],s[2],JSON.stringify(s)]"),
                             ["color", "width", UNDEFINED, '{"0":"color","1":"width"}'])
            context.eval("s.removeProperty('color');s.height='20px';s.note='value';s[Symbol.for('note')]=7")
            context.collect_garbage()
            self.assertEqual(context.eval("[s.length,s[0],s[1],Object.keys(s),s.note,s[Symbol.for('note')]]"),
                             [2, "width", "height", ["0", "1", "note"], "value", 7])
            self.assertEqual(context.eval("[Reflect.set(s,'2','bad'),s.item(2),Reflect.preventExtensions(s)]"),
                             [False, "", False])

    def test_cross_realm_getters_and_default_computed_indices(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://style.test/", "<!doctype html><iframe></iframe>")
            self.assertEqual(context.eval("""(()=>{
                const w=frames[0],e=w.document.body,s=w.getComputedStyle(e),d=w.getDefaultComputedStyle(e);
                const length=Object.getOwnPropertyDescriptor(CSSStyleDeclaration.prototype,'length').get;
                return [s[0],CSSStyleDeclaration.prototype.item.call(s,0),length.call(s),
                    JSON.stringify(s)===JSON.stringify(d),
                    Object.getPrototypeOf(s)===w.CSSStyleProperties.prototype];
            })()"""), ["accent-color", "accent-color", 393, True, True])


if __name__ == "__main__":
    unittest.main()
