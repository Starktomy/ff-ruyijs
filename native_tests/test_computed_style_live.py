"""getComputedStyle must reflect layout and subsequent DOM changes."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


SOURCE = r"""
document.body.style.margin='0';
document.body.innerHTML='<div id="container" style="width:200px;height:100px"><div id="child" style="width:50%;height:50%;padding:5px;border:2px solid"></div></div>';
const style=getComputedStyle(child), read=()=>[style.width,style.height,style.boxSizing];
const out={initial:read()};
container.style.width='300px';out.resize=read();
child.style.boxSizing='border-box';out.borderBox=read();
child.style.width='80px';child.style.display='none';out.hidden=read();
child.remove();out.detached=read();
document.body.innerHTML='<span id="inline" style="width:50%;height:30px">hello</span>';
out.inline=[getComputedStyle(inline).width,getComputedStyle(inline).height];
return out;
"""


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class ComputedStyleLiveTests(unittest.TestCase):
    def test_resolved_live_styles_match_firefox159(self):
        with Context(shell=ROOT / "dist/js") as context:
            context.load_page("https://style.test/", "<!doctype html><body>")
            actual = context.eval("(() => {" + SOURCE + "})()")
        self.assertEqual(actual, {
            "initial": ["100px", "50px", "content-box"],
            "resize": ["150px", "50px", "content-box"],
            "borderBox": ["150px", "50px", "border-box"],
            "hidden": ["80px", "50%", "border-box"],
            "detached": ["", "", ""],
            "inline": ["50%", "30px"],
        })


if __name__ == "__main__":
    unittest.main()
