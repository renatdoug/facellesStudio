"""Cenas com vídeo de fundo: validação (sem FFmpeg) e renderização de verdade (com FFmpeg)."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import main as engine
from studio import layouts, video
from studio.util import StudioError

ROOT = Path(__file__).resolve().parent.parent
HAS_FFMPEG = bool(shutil.which('ffmpeg') and shutil.which('ffprobe'))
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason='FFmpeg não encontrado')


def scene(**kw):
    return {'narration': 'Texto da cena.', **kw}


# ------------------------------------------------------------------ sem FFmpeg

def test_video_tem_prioridade_na_deteccao():
    assert layouts.detect_layout(scene(video='a.mp4')) == 'video'
    assert layouts.detect_layout(scene(video='a.mp4', prompt='x')) == 'video'
    assert layouts.detect_layout(scene(layout='video')) == 'video'  # ainda sem arquivo escolhido
    assert layouts.detect_layout(scene(prompt='x')) == 'image'


@pytest.mark.parametrize('extra, trecho', [
    ({'video_start': -1}, 'video_start'),
    ({'video_start': 'a'}, 'video_start'),
    ({'video_end': True}, 'video_end'),
    ({'video_start': 5, 'video_end': 3}, 'maior'),
    ({'video': 7}, 'video'),
])
def test_validate_script_recusa_campos_de_video_invalidos(extra, trecho):
    with pytest.raises(StudioError, match=trecho):
        engine.validate_script({'scenes': [{**scene(video='a.mp4'), **extra}]})


def test_validate_script_aceita_video_valido_e_rascunho_sem_arquivo():
    engine.validate_script({'scenes': [scene(video='a.mp4', video_start=1, video_end=4.5)]})
    engine.validate_script({'scenes': [scene(layout='video')]})  # o arquivo só é cobrado ao renderizar


def test_resolve_videos_cobra_arquivo_antes_de_renderizar(tmp_path):
    with pytest.raises(StudioError, match='nenhum arquivo'):
        engine.resolve_videos([(1, scene(layout='video'))], tmp_path)
    with pytest.raises(StudioError, match='não encontrado'):
        engine.resolve_videos([(2, scene(video='assets/media/x.mp4'))], tmp_path)
    (tmp_path / 'assets' / 'media').mkdir(parents=True)
    (tmp_path / 'assets' / 'media' / 'x.mp4').write_bytes(b'0')
    found = engine.resolve_videos([(2, scene(video='assets/media/x.mp4')), (3, scene(prompt='p'))], tmp_path)
    assert list(found) == [2]


def test_clip_window():
    assert video.clip_window(10, None, None) == (0.0, 10)
    assert video.clip_window(10, 2, 6) == (2.0, 4.0)
    assert video.clip_window(10, 2, 99) == (2.0, 8.0)  # fim além do vídeo: usa até o fim
    for start, end in ((-1, None), (10, None), (9.8, None), (1, 1.2)):
        with pytest.raises(StudioError):
            video.clip_window(10, start, end)


# ------------------------------------------------------------------ com FFmpeg de verdade

def ff(*args):
    return subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', *map(str, args)],
                          check=True, capture_output=True)


def duration(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of',
                          'default=nw=1:nk=1', str(path)], capture_output=True, text=True, check=True).stdout
    return float(out)


def frame(path, t, w=64, h=36):
    """Quadro em tons de cinza no instante t (bytes), para comparar conteúdo."""
    return subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(t), '-i', str(path), '-frames:v', '1', '-vf',
                           f'scale={w}:{h}', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'],
                          capture_output=True, check=True).stdout


def diff(a, b):
    return sum(abs(x - y) for x, y in zip(a, b)) / max(len(a), 1)


@pytest.fixture
def source_clip(tmp_path):
    """Clipe de 3 s, 4:3 (para provar o recorte central), com áudio (que deve ser descartado)."""
    path = tmp_path / 'assets' / 'media' / 'origem.mp4'
    path.parent.mkdir(parents=True)
    ff('-f', 'lavfi', '-i', 'testsrc2=duration=3:size=320x240:rate=25', '-f', 'lavfi', '-i',
       'sine=frequency=440:duration=3', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', path)
    return path


@needs_ffmpeg
def test_prepare_clip_recorta_enche_quadro_e_remove_audio(tmp_path, source_clip):
    out = video.prepare_clip(source_clip, tmp_path, 1, 640, 360, 30, start=1, end=2.5)
    probe = json.loads(subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,width,height,r_frame_rate',
         '-of', 'json', str(out)], capture_output=True, text=True, check=True).stdout)
    streams = probe['streams']
    assert [s['codec_type'] for s in streams] == ['video']  # sem áudio original
    assert (streams[0]['width'], streams[0]['height'], streams[0]['r_frame_rate']) == (640, 360, '30/1')
    assert duration(out) == pytest.approx(1.5, abs=0.15)
    stamp = out.stat().st_mtime_ns
    assert video.prepare_clip(source_clip, tmp_path, 1, 640, 360, 30, start=1, end=2.5) == out
    assert out.stat().st_mtime_ns == stamp  # cache: não refez
    other = video.prepare_clip(source_clip, tmp_path, 1, 640, 360, 30, start=0, end=2.5)
    assert other != out  # trecho diferente => outro arquivo


@needs_ffmpeg
def test_video_completo_com_loop_corte_e_cena_de_imagem(tmp_path, source_clip):
    """Render real: cartão + vídeo curto repetido (narração longa) + vídeo longo cortado."""
    long_text = ' '.join(['palavra'] * 40)  # silêncio de ~13 s com --no-voice: o clipe de 1,5 s tem de repetir
    script = {
        'channel': 'Teste', 'theme': 'health', 'fps': 25, 'subtitles': 'off', 'images': {'provider': 'none'},
        'scenes': [
            {'title': 'Cartão', 'narration': 'Abertura curta.'},
            {'title': 'Loop', 'narration': long_text, 'video': 'assets/media/origem.mp4',
             'video_start': 1, 'video_end': 2.5, 'transition': 'fade', 'headline': 'T', 'overlay_title': True},
            {'title': 'Corte', 'narration': 'Frase curta.', 'video': 'assets/media/origem.mp4'},
        ],
    }
    path = tmp_path / 'roteiro.json'
    path.write_text(json.dumps(script), encoding='utf-8')
    done = subprocess.run([sys.executable, str(ROOT / 'main.py'), '--script', str(path), '--no-voice',
                           '--res', '640x360', '--preset', 'ultrafast'], capture_output=True, text=True,
                          encoding='utf-8', errors='replace')
    assert done.returncode == 0, done.stdout + done.stderr
    assert 'Cena 2 (video)' in done.stdout and 'Cena 3 (video)' in done.stdout
    final = tmp_path / 'output' / 'video_final.mp4'
    assert final.exists()

    # a trilha tem 1 vídeo + 1 áudio (a narração), nada do áudio original do clipe
    kinds = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0',
                            str(final)], capture_output=True, text=True, check=True).stdout.split()
    assert sorted(kinds) == ['audio', 'video']
    assert duration(final) > 14

    # a cena 2 começa depois da abertura (~2 s); o vídeo continua se mexendo mesmo depois de repetir
    # (1,5 s de clipe numa cena de ~13 s)
    start2 = 2.5
    f_a, f_b, f_c = frame(final, start2 + 4.0), frame(final, start2 + 4.4), frame(final, start2 + 9.0)
    assert diff(f_a, f_b) > 1 and diff(f_b, f_c) > 1
    assert max(f_a) - min(f_a) > 40  # imagem de verdade, não um quadro chapado
