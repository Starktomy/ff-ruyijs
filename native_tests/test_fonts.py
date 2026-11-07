"""Text advance and baseline invariants that failed in the initial Linux port."""
from pathlib import Path
import sys
import os
import shutil
import subprocess
import tempfile
from unittest.mock import patch
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build native runtime first")
class FontTests(unittest.TestCase):
    def test_fontconfig_alias_preferred_and_default_bindings(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            for family in ("DejaVu Sans", "DejaVu Sans Mono"):
                font = Path(subprocess.check_output(["fc-match", "-f", "%{file}", family], text=True))
                shutil.copy2(font, directory / font.name)
            config = directory / "fonts.conf"
            config.write_text(f'''<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd">
                <fontconfig><dir>{directory}</dir>
                <alias binding="weak"><family>preferred-test</family>
                    <prefer><family>DejaVu Sans Mono</family></prefer>
                    <default><family>DejaVu Sans</family></default></alias>
                <alias binding="strong"><family>accepted-test</family>
                    <accept><family>DejaVu Sans Mono</family></accept></alias>
                <alias><family>default-only-test</family>
                    <default><family>DejaVu Sans Mono</family></default></alias>
                <alias><family>sans-serif</family><prefer><family>DejaVu Sans</family></prefer></alias>
                </fontconfig>''')
            with patch.dict(os.environ, {"FONTCONFIG_FILE": str(config)}), Context(shell=ROOT / "dist/js") as ctx:
                ctx.load_page("https://fonts.test/", "<!doctype html>")
                results = ctx.eval("""(() => {
                    const g=document.createElement('canvas').getContext('2d');
                    return ['DejaVu Sans','DejaVu Sans Mono','preferred-test','accepted-test',
                        'default-only-test, DejaVu Sans','missing-test, DejaVu Sans'].map(family=>{
                        g.font='24px '+family;const m=g.measureText('WWW iii AV');
                        return [m.width,m.actualBoundingBoxRight,m.fontBoundingBoxAscent];
                    });
                })()""")
                self.assertNotEqual(results[0], results[1])
                self.assertEqual(results[2:4], [results[1]] * 2)
                self.assertEqual(results[4:], [results[0]] * 2)

    def test_shared_font_caches_follow_profiles_and_frame_lifetimes(self):
        snapshots = []
        for family in ("DejaVu Sans", "DejaVu Sans Mono", "DejaVu Sans"):
            with self.subTest(family=family), Context(shell=ROOT / "dist/js") as ctx:
                ctx.configure_fingerprint({"fonts": {"serif": family}})
                ctx.load_page("https://fonts.test/", "<html><body></body></html>")
                ctx.eval("""globalThis.measure = function(doc) {
                    const c=doc.createElement('canvas');c.width=240;c.height=60;
                    const g=c.getContext('2d');g.font='24px serif';
                    const text='AV e\\u0301 WWW iii';g.fillText(text,5,40);
                    const m=g.measureText(text),p=g.getImageData(0,0,240,60).data;
                    let hash=0;for(let i=0;i<p.length;i++)hash=(hash*31+p[i])>>>0;
                    return [m.width,m.actualBoundingBoxLeft,m.actualBoundingBoxRight,
                        m.fontBoundingBoxAscent,m.fontBoundingBoxDescent,hash];
                };
                globalThis.framesToTest=[];
                for(let i=0;i<2;i++){
                    const f=document.createElement('iframe');f.srcdoc='<!doctype html>';
                    document.body.appendChild(f);framesToTest.push(f);
                }""")
                ctx.advance(10)
                got = ctx.eval("[measure(document),...framesToTest.map(f=>measure(f.contentDocument))]")
                self.assertEqual(got, [got[0]] * 3)
                snapshots.append(got[0])
                ctx.eval("framesToTest.forEach(f=>f.remove());framesToTest=[]")
                ctx.collect_garbage()
                self.assertEqual(ctx.eval("measure(document)"), got[0])
                for _ in range(2):
                    ctx.load_page("https://fonts.test/next", "<html><body></body></html>")
                    width = ctx.eval("""(() => {
                        const g=document.createElement('canvas').getContext('2d');
                        g.font='24px serif';return g.measureText('AV e\\u0301 WWW iii').width;
                    })()""")
                    self.assertEqual(width, got[0][0])
        self.assertNotEqual(snapshots[0], snapshots[1])
        self.assertEqual(snapshots[0], snapshots[2])

    def test_empty_text_baselines_kerning_and_combining_marks(self):
        with Context(shell=ROOT / "dist/js") as ctx:
            ctx.load_page("https://fonts.test/", "<html><body></body></html>")
            got = ctx.eval("""(() => {
              const g=document.createElement('canvas').getContext('2d');g.font='32px DejaVu Sans';
              const empty=g.measureText(''), space=g.measureText(' '), e=g.measureText('e');
              return {empty:[empty.width,empty.fontBoundingBoxAscent,empty.fontBoundingBoxDescent],
                baselines:[empty.hangingBaseline,empty.alphabeticBaseline,empty.ideographicBaseline],
                space:[space.width,space.actualBoundingBoxLeft,space.actualBoundingBoxRight],
                kern:g.measureText('AV').width<g.measureText('A').width+g.measureText('V').width,
                mark:g.measureText('e\\u0301').width-e.width,
                trailing:g.measureText('A ').width-g.measureText('A').width};
            })()""")
            self.assertEqual(got["empty"][0], 0)
            self.assertGreater(got["empty"][1], 0)
            self.assertGreater(got["empty"][2], 0)
            self.assertGreater(got["baselines"][0], 0)
            self.assertEqual(got["baselines"][1], 0)
            self.assertLess(got["baselines"][2], 0)
            self.assertEqual(got["space"][1:], [0, 0])
            self.assertTrue(got["kern"])
            self.assertAlmostEqual(got["mark"], 0, places=5)
            self.assertAlmostEqual(got["trailing"], got["space"][0], places=4)

    def test_synthetic_styles_with_regular_font_only(self):
        font = Path(subprocess.check_output(["fc-match", "-f", "%{file}", "DejaVu Sans:style=Book"], text=True))
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            shutil.copy2(font, directory / "regular.ttf")
            config = directory / "fonts.conf"
            config.write_text(f'<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig><dir>{directory}</dir></fontconfig>')
            with patch.dict(os.environ, {"FONTCONFIG_FILE": str(config)}), Context(shell=ROOT / "dist/js") as ctx:
                ctx.load_page("https://fonts.test/", "<html><body></body></html>")
                got = ctx.eval("""(() => {
                    const c=document.createElement('canvas');c.width=220;c.height=90;
                    const g=c.getContext('2d');const results=[];
                    for(const style of ['', 'italic ', 'bold ']){
                        g.clearRect(0,0,220,90);g.font=style+'40px DejaVu Sans';g.fillText('Native',20,60);
                        const m=g.measureText('Native');const p=g.getImageData(0,0,220,90).data;
                        let alpha=0,hash=0;for(let i=0;i<p.length;i++){hash=(hash*31+p[i])>>>0;if(i%4===3)alpha+=p[i]}
                        results.push({width:m.width,left:m.actualBoundingBoxLeft,right:m.actualBoundingBoxRight,alpha,hash});
                    }return results;
                })()""")
                self.assertAlmostEqual(got[0]['width'],got[1]['width'],places=4)
                self.assertNotEqual(got[0]['hash'],got[1]['hash'])
                self.assertGreater(got[2]['alpha'],got[0]['alpha'])
                self.assertGreaterEqual(got[2]['width'],got[0]['width'])

    @unittest.skipUnless(Path('/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf').is_file(), 'install Noto Color Emoji')
    def test_color_emoji_preserves_palette(self):
        with Context(shell=ROOT / "dist/js") as ctx:
            ctx.load_page("https://fonts.test/", "<html><body></body></html>")
            got=ctx.eval("""(() => {
                const c=document.createElement('canvas');c.width=100;c.height=100;const g=c.getContext('2d');
                g.font='64px "Noto Color Emoji"';const results=[];
                for(const fill of ['red','blue']){
                    g.clearRect(0,0,100,100);g.fillStyle=fill;g.fillText('😀',5,70);
                    const p=g.getImageData(0,0,100,100).data;let hash=0,colors=0;
                    for(let i=0;i<p.length;i++){hash=(hash*31+p[i])>>>0;
                        if(i%4===0&&p[i+3]&&p[i]!==p[i+1])colors++}
                    results.push({hash,colors});
                }return results;
            })()""")
            self.assertGreater(got[0]['colors'],100)
            self.assertEqual(got[0]['hash'],got[1]['hash'])



if __name__ == "__main__":
    unittest.main()
