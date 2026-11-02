"""Document.title follows the first HTML title in the document tree."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class DocumentTitleTests(unittest.TestCase):
    def test_moved_title_is_read_and_updated_in_place(self):
        with Context(shell=ROOT / "dist/js") as c:
            c.load_page('https://title.test/', '<!doctype html><title>Original</title><body></body>')
            self.assertEqual(c.eval(r'''(() => {
                const title=document.querySelector('title');document.body.appendChild(title);
                title.textContent='  First\n  title  ';
                const read=document.title;
                document.title='Replaced';
                return [read,document.title,title.textContent,title.parentNode===document.body,
                    document.querySelectorAll('title').length];
            })()'''), ['First title', 'Replaced', 'Replaced', True, 1])

    def test_tree_order_excludes_shadow_and_non_html_titles(self):
        with Context(shell=ROOT / "dist/js") as c:
            c.load_page('https://title.test/', '<!doctype html><title>Head</title><body></body>')
            self.assertEqual(c.eval('''(() => {
                const host=document.createElement('div');document.body.appendChild(host);
                host.attachShadow({mode:'open'}).innerHTML='<title>Shadow</title>';
                const svg=document.createElementNS('http://www.w3.org/2000/svg','title');
                svg.textContent='SVG';document.documentElement.prepend(svg);
                const first=document.createElement('title');first.textContent='First';
                document.documentElement.prepend(first);
                const read=document.title;first.remove();const fallback=document.title;
                document.querySelector('head title').remove();const absent=document.title;
                document.title='Created';
                return [read,fallback,absent,document.title,document.head.querySelectorAll('title').length];
            })()'''), ['First', 'Head', '', 'Created', 1])


if __name__ == '__main__':
    unittest.main()
