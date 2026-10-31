"""Trusted Types default policies run at the destination realm's sinks."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context

CSP = '<meta http-equiv="Content-Security-Policy" content="require-trusted-types-for \'script\'">'


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class TrustedSinkTests(unittest.TestCase):
    def test_default_policy_is_inactive_without_an_enforcing_directive(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://trusted.test/", "<!doctype html>")
            self.assertEqual(context.eval("""(()=>{let count=0;
                trustedTypes.createPolicy('default',{createHTML(s){count++;return s},
                    createScript(s){count++;return s},createScriptURL(s){count++;return s}});
                const e=document.createElement('div'),s=document.createElement('script');
                e.innerHTML='<b>plain</b>';s.src='data:,0';
                return [window.eval('2+3'),count,e.textContent,s.src];})()"""),
                             [5, 0, "plain", "data:,0"])

    def test_required_sinks_reject_strings_and_accept_exact_trusted_brands(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://trusted.test/", "<!doctype html>" + CSP)
            self.assertEqual(context.eval("""(()=>{
                const e=document.createElement('div'),s=document.createElement('script');
                const error=fn=>{try{fn();return 'allowed'}catch(e){return e.name}};
                const before=[error(()=>e.innerHTML='bad'),error(()=>s.src='data:,0'),
                    error(()=>window.eval('0')),e.innerHTML,s.getAttribute('src')];
                const p=trustedTypes.createPolicy('values',{createHTML:s=>s,
                    createScript:s=>s,createScriptURL:s=>s});
                const html=p.createHTML('<b>safe</b>');html.toString=()=>{throw 1};
                e.innerHTML=html;s.src=p.createScriptURL('data:,0');
                return [before,e.textContent,s.src,window.eval(p.createScript('2+3')),
                    error(()=>e.innerHTML=p.createScript('bad'))];})()"""),
                             [["TypeError", "TypeError", "EvalError", "", None],
                              "safe", "data:,0", 5, "TypeError"])

    def test_cross_realm_factory_and_default_callbacks_use_the_receiver(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://trusted.test/", "<!doctype html>" + CSP + "<iframe></iframe>")
            self.assertEqual(context.eval("""(()=>{
                const w=frames[0],d=w.document,calls=[];let mask=0;
                const p=trustedTypes.createPolicy.call(w.trustedTypes,'default',{
                    createHTML(...a){mask|=1;calls.push(a);return a[0]},
                    createScript(...a){mask|=2;calls.push(a);return a[0]},
                    createScriptURL(...a){mask|=4;calls.push(a);return a[0]}});
                const e=d.createElement('div'),s=d.createElement('script');
                e.innerHTML='<b>t</b>';const result=w.eval('0');s.src='data:,0';
                return [mask,calls,result,e.innerHTML,s.src,
                    Object.getPrototypeOf(p)===w.TrustedTypePolicy.prototype,
                    w.trustedTypes.defaultPolicy===p,trustedTypes.defaultPolicy===null];})()"""),
                             [7, [["<b>t</b>", "TrustedHTML", "Element innerHTML"],
                                  ["0", "TrustedScript", "eval"],
                                  ["data:,0", "TrustedScriptURL", "HTMLScriptElement src"]],
                              0, "<b>t</b>", "data:,0", True, True, True])

    def test_default_callback_results_exceptions_and_eval_code_identity(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://trusted.test/", "<!doctype html>" + CSP)
            self.assertEqual(context.eval("""(()=>{
                const e=document.createElement('div'),calls=[],sentinel={};
                const error=fn=>{try{fn();return 'allowed'}catch(e){return e===sentinel?'sentinel':e.name}};
                trustedTypes.createPolicy('default',{
                    createHTML(s,type,sink){calls.push([s,type,sink]);
                        if(s==='reject')return null;if(s==='throw')throw sentinel;return '<i>converted</i>'},
                    createScript:s=>'1+1'});
                e.innerHTML=null;const first=e.innerHTML;
                const rejected=error(()=>e.innerHTML='reject'),thrown=error(()=>e.innerHTML='throw');
                const script=error(()=>document.createElement('script').src='data:,0');
                const changed=error(()=>window.eval('2+3')),same=window.eval('1+1');
                return [first,e.innerHTML,rejected,thrown,script,changed,same,calls];})()"""),
                             ["<i>converted</i>", "<i>converted</i>", "TypeError", "sentinel",
                              "TypeError", "EvalError", 2,
                              [["", "TrustedHTML", "Element innerHTML"],
                               ["reject", "TrustedHTML", "Element innerHTML"],
                               ["throw", "TrustedHTML", "Element innerHTML"]]])

    def test_policy_allow_lists_duplicates_and_document_reset(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://trusted.test/", '<!doctype html><meta http-equiv="Content-Security-Policy" '
                              'content="trusted-types allowed default">')
            self.assertEqual(context.eval("""(()=>{
                const error=n=>{try{trustedTypes.createPolicy(n,{});return 'allowed'}catch(e){return e.name}};
                return [error('denied'),error('allowed'),error('allowed'),error('Allowed'),
                    error('default'),error('default')];})()"""),
                             ["TypeError", "allowed", "TypeError", "TypeError", "allowed", "TypeError"])
            context.put_resource("https://trusted.test/next", '<!doctype html><meta http-equiv="Content-Security-Policy" '
                                 'content="trusted-types allowed \'allow-duplicates\'">',
                                 headers=[["Content-Type", "text/html"]])
            context.navigate("https://trusted.test/next")
            context.advance(10)
            context.collect_garbage()
            self.assertEqual(context.eval("[trustedTypes.defaultPolicy,"
                                          "trustedTypes.createPolicy('allowed',{}).name,"
                                          "trustedTypes.createPolicy('allowed',{}).name]"),
                             [None, "allowed", "allowed"])


if __name__ == "__main__":
    unittest.main()
