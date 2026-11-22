"""O .env do canal (pasta do roteiro) deve ter prioridade sobre o .env da instalação."""
import os
import unittest
from pathlib import Path

from studio import images_ai


class DotenvPriorityTest(unittest.TestCase):
    def setUp(self):
        for k in ('FS_SHARED_ONLY', 'FS_OVERRIDE_ME'):
            os.environ.pop(k, None)

    def test_project_env_wins_over_install_env(self, tmp_path=None):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            install_dir, project_dir = Path(d) / 'instalacao', Path(d) / 'canais' / 'geeklab'
            project_dir.mkdir(parents=True)
            (install_dir).mkdir()
            (install_dir / '.env').write_text('FS_SHARED_ONLY=do_padrao\nFS_OVERRIDE_ME=valor_padrao\n')
            (project_dir / '.env').write_text('FS_OVERRIDE_ME=valor_do_canal\n')
            # Mesma ordem usada em main(): primeiro o do projeto, depois o da instalação.
            images_ai.load_dotenv(project_dir / '.env')
            images_ai.load_dotenv(install_dir / '.env')
            self.assertEqual(os.environ['FS_OVERRIDE_ME'], 'valor_do_canal')
            self.assertEqual(os.environ['FS_SHARED_ONLY'], 'do_padrao')


if __name__ == '__main__':
    unittest.main()
