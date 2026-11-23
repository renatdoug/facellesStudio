"""Testes da geração de imagens contra APIs simuladas (sem internet, sem custo)."""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from studio import images_ai
from tests import fake_apis


class ImagesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, cls.url = fake_apis.start()
        os.environ.update({
            'OPENAI_API_KEY': 'test-openai', 'OPENAI_BASE_URL': cls.url + '/v1',
            'GEMINI_API_KEY': 'test-gemini', 'GEMINI_BASE_URL': cls.url,
            'POLLINATIONS_FREE_URL': cls.url, 'POLLINATIONS_FREE_INTERVAL': '0'})
        os.environ.pop('POLLINATIONS_API_KEY', None)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        fake_apis.State.requests.clear()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def bank(self, **settings):
        return images_ai.ImageBank(self.dir, settings)

    def test_openai(self):
        path, new = self.bank(provider='openai', style='flat').get('01', 'uma UTI')
        self.assertTrue(new)
        self.assertEqual(path.read_bytes()[:4], b'\x89PNG')
        body = fake_apis.State.requests[-1][3]
        self.assertEqual(body['model'], 'gpt-image-2')
        self.assertIn('uma UTI, flat, no text', body['prompt'])

    def test_gemini_falls_back_to_other_config_name(self):
        path, _ = self.bank(provider='gemini').get('01', 'monitor')
        self.assertTrue(path.exists())
        posts = [r for r in fake_apis.State.requests if r[0] == 'POST']
        self.assertEqual(len(posts), 2)  # 1ª recusada (400), 2ª aceita
        self.assertIn('/v1/models/gemini-3.1-flash-image:generateContent', posts[1][1])

    def test_gemini_aceita_imagem_de_referencia_e_sufixo_proprio(self):
        ref = fake_apis.fake_png(64, 64)
        cfg = {**images_ai.DEFAULTS['gemini'], 'aspect': '3:4', 'references': [('image/png', ref)], 'prompt_suffix': ''}
        data = images_ai.gen_gemini('same character, happy', cfg, 1)
        self.assertEqual(data[:4], b'\x89PNG')
        parts = [r for r in fake_apis.State.requests if r[0] == 'POST'][-1][3]['contents'][0]['parts']
        self.assertEqual(len(parts), 2)  # referência primeiro, texto depois
        self.assertEqual(parts[0]['inlineData']['mimeType'], 'image/png')
        self.assertEqual(parts[1]['text'], 'same character, happy')  # sem "Widescreen 16:9" quando o sufixo é ''
        # sem referências nem sufixo: o comportamento de sempre (um único texto, com o sufixo padrão)
        images_ai.gen_gemini('um monitor', dict(images_ai.DEFAULTS['gemini']), 1)
        parts = [r for r in fake_apis.State.requests if r[0] == 'POST'][-1][3]['contents'][0]['parts']
        self.assertEqual(parts, [{'text': 'um monitor. Widescreen 16:9 composition.'}])

    def test_pollinations_free(self):
        path, _ = self.bank(provider='pollinations').get('01', 'leito vazio')
        self.assertTrue(path.exists())
        q = fake_apis.State.requests[-1][3]
        self.assertEqual(q['width'], ['1920'])
        self.assertEqual(q['seed'], ['1234'])

    def test_comfyui_fills_placeholders(self):
        wf = self.dir / 'comfyui'
        wf.mkdir()
        shutil.copy(Path(__file__).resolve().parents[1] / 'comfyui' / 'sdxl_api.json', wf / 'sdxl_api.json')
        path, _ = self.bank(provider='comfyui', url=self.url, seed=7).get('01', 'sala de UTI')
        self.assertTrue(path.exists())
        sent = fake_apis.State.last_comfy
        self.assertEqual(sent['3']['inputs']['seed'], 7)        # inteiro, não texto
        self.assertEqual(sent['5']['inputs']['width'], 1344)
        self.assertIn('sala de UTI', sent['6']['inputs']['text'])

    def test_comfyui_workflow_falls_back_to_install_dir(self):
        """Um roteiro em outra pasta (outro canal) ainda encontra o workflow padrão
        que veio junto da instalação, sem precisar copiá-lo para cada projeto."""
        install_dir = Path(__file__).resolve().parents[1]
        bank = images_ai.ImageBank(self.dir, {'provider': 'comfyui', 'url': self.url, 'seed': 3},
                                   install_dir=install_dir)
        path, _ = bank.get('01', 'sala de UTI')
        self.assertTrue(path.exists())
        self.assertFalse((self.dir / 'comfyui').exists())  # nada foi copiado para o projeto

    def test_cache_and_regen(self):
        b = self.bank(provider='pollinations')
        p1, new1 = b.get('01', 'leito')
        p2, new2 = self.bank(provider='pollinations').get('01', 'leito')  # nova execução lê o manifesto
        self.assertTrue(new1)
        self.assertFalse(new2)
        self.assertEqual(p1, p2)
        p3, new3 = b.get('01', 'leito', regen=True)
        self.assertTrue(new3)
        self.assertNotEqual(p1, p3)
        manifest = json.loads((self.dir / 'assets' / 'generated' / 'manifest.json').read_text())
        self.assertEqual(manifest['01']['file'], p3.name)

    def test_prompt_change_regenerates(self):
        b = self.bank(provider='pollinations')
        b.get('01', 'leito')
        _, new = b.get('01', 'leito com monitor')
        self.assertTrue(new)

    def test_missing_key_message(self):
        old = os.environ.pop('OPENAI_API_KEY')
        try:
            with self.assertRaises(images_ai.ImageGenError) as cm:
                self.bank(provider='openai').get('01', 'x')
            self.assertIn('OPENAI_API_KEY', str(cm.exception))
        finally:
            os.environ['OPENAI_API_KEY'] = old

    def test_provider_none(self):
        with self.assertRaises(images_ai.ImageGenError):
            self.bank(provider='none').get('01', 'x')

    def test_dotenv(self):
        env = self.dir / '.env'
        env.write_text('# chaves\nFS_TEST_KEY="abc"\n', encoding='utf-8')
        images_ai.load_dotenv(env)
        self.assertEqual(os.environ.get('FS_TEST_KEY'), 'abc')


if __name__ == '__main__':
    unittest.main()
