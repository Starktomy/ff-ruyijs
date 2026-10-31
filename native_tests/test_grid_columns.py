"""Numeric grid placements create implicit columns and contribute intrinsic size."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class GridColumnTests(unittest.TestCase):
    def context(self, html):
        context = Context(shell=ROOT / "dist/js")
        self.addCleanup(context.close)
        context.load_page("https://grid.test/", "<!doctype html><style>body{margin:0}</style>" + html)
        return context

    def test_intrinsic_grid_in_flex_keeps_the_second_column_beside_the_first(self):
        context = self.context("""<div style="display:flex"><label id="grid"
            style="display:grid;position:relative;place-items:center">
            <input type="checkbox" style="position:absolute;inset:0;width:100%;height:100%;margin:0">
            <span id="box" style="grid-area:1/1;width:24px;height:24px"></span>
            <span id="label" style="grid-column:2;margin-left:8px;width:120px;height:16px"></span>
            </label></div>""")
        self.assertEqual(context.eval("""['grid','box','label'].map(id=>{
            const r=document.getElementById(id).getBoundingClientRect();return [r.x,r.y,r.width,r.height];})"""),
            [[0, 0, 152, 24], [0, 0, 24, 24], [32, 4, 120, 16]])
        self.assertEqual(context.eval("""(()=>{const r=document.querySelector('input').getBoundingClientRect();
            return [r.width,r.height]})()"""), [152, 24])

    def test_explicit_placements_can_overlap_and_implicit_tracks_use_auto_columns(self):
        context = self.context("""<div id="grid" style="display:grid;width:200px;
            grid-template-columns:40px;grid-auto-columns:60px;column-gap:10px">
            <div id="a" style="grid-area:1/2;width:20px;height:10px"></div>
            <div id="b" style="grid-area:1/2;width:30px;height:20px"></div></div>""")
        self.assertEqual(context.eval("""['a','b'].map(id=>{const r=document.getElementById(id).getBoundingClientRect();
            return [r.x,r.y,r.width,r.height]})"""), [[50, 0, 20, 10], [50, 0, 30, 20]])

    def test_place_items_expands_cascades_and_serializes(self):
        context = self.context("""<style>#grid{display:grid;place-items:center end;width:100px;height:80px}
            #child{width:20px;height:10px}</style><div id="grid"><div id="child"></div></div>""")
        self.assertEqual(context.eval("""(()=>{const e=document.querySelector('#child'),r=e.getBoundingClientRect();
            const style=document.querySelector('style:last-of-type').sheet.cssRules[0].style;
            return [r.x,r.y,style.getPropertyValue('place-items'),style.getPropertyValue('align-items'),
                style.getPropertyValue('justify-items')]})()"""), [80, 35, "center end", "center", "end"])
        self.assertEqual(context.eval("""(()=>{const style=document.querySelector('#grid').style;
            style.setProperty('place-items','start center','important');
            const result=[style.getPropertyValue('place-items'),style.getPropertyPriority('align-items')];
            style.removeProperty('place-items');return [...result,style.getPropertyValue('justify-items')];})()"""),
            ["start center", "important", ""])


if __name__ == "__main__":
    unittest.main()
