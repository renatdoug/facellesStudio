"""Testes dos layouts: geram fundo + eventos ASS sem precisar do FFmpeg."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from studio import layouts, visuals
from studio.subtitles import Word, ass_time

ROOT = Path(__file__).resolve().parents[1]


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.fonts = {'bold': visuals.find_font(True), 'regular': visuals.find_font(False)}

    def tearDown(self):
        shutil.rmtree(self.dir)

    def ctx(self, scene):
        words = [Word(t, 0.5 + i * 0.4, 0.8 + i * 0.4) for i, t in enumerate(scene['narration'].split())]
        return layouts.Ctx(scene, 1, 1280, 720, 'health', 'Canal', self.fonts,
                           visuals.font_family(self.fonts['bold']), words, 0.5, words[-1].end, words[-1].end + 0.5)

    def test_example_script_layouts(self):
        data = json.loads((ROOT / 'exemplo_layouts.json').read_text(encoding='utf-8'))
        seen = set()
        for scene in data['scenes']:
            name = layouts.detect_layout(scene)
            seen.add(name)
            bg = self.dir / f'{name}.png'
            styles, events = layouts.BUILDERS[name](self.ctx(scene), bg)
            self.assertTrue(bg.exists())
            self.assertTrue(styles and events, name)
        self.assertEqual(seen, {'number', 'chart', 'compare', 'quote'})

    def test_list_reveals_in_order_of_words(self):
        scene = {'narration': 'primeiro vem alfa depois beta e por fim gama',
                 'headline': 'LISTA', 'items': [{'text': 'Alfa', 'on_word': 'alfa'},
                                                {'text': 'Beta', 'on_word': 'beta'},
                                                {'text': 'Gama', 'on_word': 'gama'}]}
        c = self.ctx(scene)
        _, events = layouts.layout_list(c, self.dir / 'l.png')
        starts = [e.split(',')[1] for e in events if ',LItem,' in e and 'move' in e]
        self.assertEqual(starts, sorted(starts))
        alfa = next(w for w in c.words if w.text == 'alfa')
        self.assertEqual(starts[0], ass_time(alfa.start))

    def test_detect_layout(self):
        self.assertEqual(layouts.detect_layout({'prompt': 'x'}), 'image')
        self.assertEqual(layouts.detect_layout({'items': ['a']}), 'list')
        self.assertEqual(layouts.detect_layout({}), 'card')
        self.assertEqual(layouts.detect_layout({'layout': 'card', 'items': ['a']}), 'card')


if __name__ == '__main__':
    unittest.main()
