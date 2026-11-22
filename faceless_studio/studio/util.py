"""Funções utilitárias: execução do FFmpeg, durações e checagem do ambiente."""
import shutil
import subprocess
from pathlib import Path


class StudioError(RuntimeError):
    """Erro com mensagem amigável para o usuário."""


def run(cmd, cwd=None):
    """Executa um comando e devolve o stdout; levanta StudioError com o final do stderr."""
    cmd = [str(c) for c in cmd]
    p = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       text=True, encoding='utf-8', errors='replace')
    if p.returncode:
        raise StudioError(f"Falha no comando:\n{' '.join(cmd)}\n\n{p.stderr[-2500:]}")
    return p.stdout


def media_duration(path):
    out = run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
               '-of', 'default=noprint_wrappers=1:nokey=1', path])
    return float(out.strip())


REQUIRED_FILTERS = ('ass', 'zoompan', 'sidechaincompress', 'loudnorm', 'fade')


def check_ffmpeg():
    """Confirma que FFmpeg/ffprobe existem e têm os filtros usados pelo projeto."""
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise StudioError('FFmpeg e ffprobe não encontrados. Instale o FFmpeg e adicione-o ao PATH.')
    filters = run(['ffmpeg', '-hide_banner', '-filters'])
    missing = [f for f in REQUIRED_FILTERS if f' {f} ' not in filters]
    if missing:
        raise StudioError('Seu FFmpeg não tem os filtros: ' + ', '.join(missing) +
                          '. Use uma build completa (ex.: gyan.dev "full" no Windows).')
    encoders = run(['ffmpeg', '-hide_banner', '-encoders'])
    if 'libx264' not in encoders:
        raise StudioError('Seu FFmpeg não tem o codificador libx264.')


def ensure_dir(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path
