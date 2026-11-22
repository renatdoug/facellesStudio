"""Testes das legendas. Rode na pasta do projeto: python -m unittest -v"""
import unittest

from studio.subtitles import (Word, align_words, ass_time, chunk_times, chunk_words,
                              find_word_time, srt_time)


class AlignTests(unittest.TestCase):
    def test_keeps_punctuation_and_times(self):
        events = [[0.1, 0.4, 'Olá'], [0.5, 0.9, 'mundo']]
        words = align_words('Olá, mundo!', events, 1.0)
        self.assertEqual([w.text for w in words], ['Olá,', 'mundo!'])
        self.assertAlmostEqual(words[1].start, 0.5)

    def test_accent_and_case_insensitive(self):
        words = align_words('Atenção UTI', [[0, .3, 'atencao'], [.4, .7, 'uti']], 1)
        self.assertAlmostEqual(words[1].start, 0.4)

    def test_missing_word_is_interpolated(self):
        events = [[0.0, 0.3, 'um'], [1.0, 1.3, 'três']]
        words = align_words('um dois três', events, 1.5)
        self.assertTrue(0.3 <= words[1].start < 1.0)

    def test_compound_word_split_by_voice(self):
        events = [[0, .3, 'pronto'], [.3, .6, 'socorro'], [.7, 1, 'cheio']]
        words = align_words('pronto-socorro cheio', events, 1.2)
        self.assertEqual(len(words), 2)
        self.assertAlmostEqual(words[0].end, 0.6)
        self.assertAlmostEqual(words[1].start, 0.7)

    def test_short_word_not_stolen_by_previous(self):
        events = [[0, .4, 'paciente'], [.5, .6, 'a'], [.7, 1, 'sala']]
        words = align_words('paciente a sala', events, 1.2)
        self.assertAlmostEqual(words[1].start, 0.5)

    def test_no_events_fallback(self):
        words = align_words('a bb ccc', [], 6.0)
        self.assertAlmostEqual(words[-1].end, 6.0)


class ChunkTests(unittest.TestCase):
    def mk(self, text):
        return [Word(t, i * .4, i * .4 + .3) for i, t in enumerate(text.split())]

    def test_limits(self):
        chunks = chunk_words(self.mk('palavra ' * 30))
        self.assertTrue(all(len(c) <= 7 for c in chunks))
        self.assertTrue(all(len(' '.join(w.text for w in c)) <= 38 for c in chunks))

    def test_breaks_after_punctuation(self):
        chunks = chunk_words(self.mk('Primeiro vem isto, depois aquilo.'))
        self.assertEqual(chunks[0][-1].text, 'isto,')

    def test_no_dangling_preposition(self):
        chunks = chunk_words(self.mk('Quando um paciente chega à unidade de terapia intensiva agora'))
        self.assertNotIn(chunks[0][-1].text.lower(), {'de', 'à', 'um'})

    def test_times_do_not_overlap(self):
        chunks = chunk_words(self.mk('um dois três quatro cinco seis sete oito nove dez onze'))
        times = chunk_times(chunks, 10)
        for (a1, b1), (a2, _) in zip(times, times[1:]):
            self.assertLessEqual(b1, a2 + 1e-9)


class FormatTests(unittest.TestCase):
    def test_ass_time(self):
        self.assertEqual(ass_time(3723.456), '1:02:03.46')

    def test_srt_time(self):
        self.assertEqual(srt_time(3723.456), '01:02:03,456')

    def test_find_word_time(self):
        words = [Word('Comunicação', 2.0, 2.5)]
        self.assertEqual(find_word_time(words, 'comunicacao', 0), 2.0)
        self.assertEqual(find_word_time(words, 'inexistente', 0.6), 0.6)


if __name__ == '__main__':
    unittest.main()
