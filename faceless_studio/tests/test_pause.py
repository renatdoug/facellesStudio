"""Pausa entre cenas: corte do silêncio que o edge-tts deixa depois da fala e o campo "pause"."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import main as engine
from studio import voice
from studio.util import StudioError

ROOT = Path(__file__).resolve().parent.parent
needs_ffmpeg = pytest.mark.skipif(not (shutil.which('ffmpeg') and shutil.which('ffprobe')),
                                  reason='FFmpeg não encontrado')


def ff(*args):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', *map(str, args)], check=True, capture_output=True)


def duration(path):
    return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of',
                                 'default=nw=1:nk=1', str(path)], capture_output=True, text=True,
                                check=True).stdout)


def tone_then_silence(path, lead=0.0, tone=1.5, tail=1.0):
    """Áudio sintético: `lead` s de silêncio, `tone` s de "fala" (seno) e `tail` s de silêncio no fim."""
    parts, labels = [], []
    if lead:
        parts.append(f'aevalsrc=0:d={lead}:s=44100[l]')
        labels.append('[l]')
    parts.append(f'sine=frequency=440:duration={tone}:sample_rate=44100[t]')
    labels.append('[t]')
    if tail:
        parts.append(f'aevalsrc=0:d={tail}:s=44100[e]')
        labels.append('[e]')
    graph = ';'.join(parts) + f';{"".join(labels)}concat=n={len(labels)}:v=0:a=1[a]'
    ff('-filter_complex', graph, '-map', '[a]', '-ac', 1, path)


# ------------------------------------------------------------------ medição do silêncio final

@needs_ffmpeg
def test_acha_onde_comeca_o_silencio_final(tmp_path):
    a = tmp_path / 'a.wav'
    tone_then_silence(a, lead=0.2, tone=1.5, tail=1.0)
    assert voice.trailing_silence_start(a) == pytest.approx(1.7, abs=0.12)
    b = tmp_path / 'b.wav'
    tone_then_silence(b, tone=1.5, tail=0)  # sem silêncio final
    assert voice.trailing_silence_start(b) is None


@needs_ffmpeg
def test_speech_seconds_corta_o_silencio_mas_nunca_a_fala(tmp_path):
    a = tmp_path / 'a.wav'
    tone_then_silence(a, lead=0.2, tone=1.5, tail=1.0)  # fala até ~1,7 s; arquivo de ~2,7 s
    dur = duration(a)
    # só pelo áudio (sem eventos): fim da fala + folga
    assert voice.speech_seconds(a, [], dur) == pytest.approx(1.7 + voice.SPEECH_PAD, abs=0.12)
    # evento dizendo que a fala vai até 1,6 s: vale o maior (o áudio mostra 1,7 s)
    assert voice.speech_seconds(a, [[0.2, 1.6, 'x']], dur) == pytest.approx(1.7 + voice.SPEECH_PAD, abs=0.12)
    # evento dizendo que a fala vai até 2,3 s (áudio "silencioso" ali): nunca corta antes do evento
    assert voice.speech_seconds(a, [[0.2, 2.3, 'x']], dur) == pytest.approx(2.3 + voice.SPEECH_PAD, abs=0.02)
    # nunca passa da duração do arquivo
    assert voice.speech_seconds(a, [[0, 99, 'x']], dur) == dur


@needs_ffmpeg
def test_sem_silencio_final_e_sem_eventos_mantem_a_duracao(tmp_path):
    b = tmp_path / 'b.wav'
    tone_then_silence(b, tone=1.5, tail=0)
    assert voice.speech_seconds(b, [], duration(b)) == pytest.approx(duration(b))


# ------------------------------------------------------------------ campo "pause"

@pytest.mark.parametrize('value', [-1, 5, 'curta', True, [0.2]])
def test_pause_invalida_e_recusada(value):
    with pytest.raises(StudioError, match='pause'):
        engine.validate_script({'pause': value, 'scenes': [{'narration': 'x'}]})


@pytest.mark.parametrize('value', [0, 0.1, 0.2, 1, 3])
def test_pause_valida_e_aceita(value):
    engine.validate_script({'pause': value, 'scenes': [{'narration': 'x'}]})


def render(tmp_path, script, name):
    path = tmp_path / f'{name}.json'
    path.write_text(json.dumps(script), encoding='utf-8')
    done = subprocess.run([sys.executable, str(ROOT / 'main.py'), '--script', str(path), '--no-voice',
                           '--res', '320x180', '--preset', 'ultrafast', '--output', f'output/{name}.mp4'],
                          capture_output=True, text=True, encoding='utf-8', errors='replace')
    assert done.returncode == 0, done.stdout + done.stderr
    return duration(tmp_path / 'output' / f'{name}.mp4')


@needs_ffmpeg
def test_pause_controla_a_pausa_depois_de_cada_cena(tmp_path):
    scenes = [{'narration': 'Primeira cena.', 'transition': 'cut'}, {'narration': 'Segunda cena.', 'transition': 'cut'},
              {'narration': 'Terceira cena.', 'transition': 'cut'}]
    base = {'channel': 'T', 'fps': 25, 'subtitles': 'off', 'images': {'provider': 'none'}, 'scenes': scenes}
    curta = render(tmp_path, {**base, 'pause': 0.0}, 'curta')
    longa = render(tmp_path, {**base, 'pause': 1.0}, 'longa')
    # Cenas 1 e 2: +1,0 s cada. A última sai com fade (piso de 0,55 s): 0,55 -> 1,0 = +0,45 s. Total +2,45 s.
    assert longa - curta == pytest.approx(2.45, abs=0.2), (curta, longa)


@needs_ffmpeg
def test_render_com_voz_em_cache_nao_conta_o_silencio_final(tmp_path):
    """Com a narração já em cache (sem rede), o silêncio de ~1 s depois da última palavra é descartado."""
    text, voz, rate = 'Olá mundo', 'pt-BR-AntonioNeural', '+0%'
    cache = tmp_path / 'temp' / 'cache'
    cache.mkdir(parents=True)
    key = voice._key(text, voz, rate)
    wav = tmp_path / 'fala.wav'
    tone_then_silence(wav, lead=0.2, tone=1.2, tail=1.0)  # fala 0,2 s a 1,4 s; arquivo de 2,4 s
    ff('-i', wav, '-c:a', 'libmp3lame', cache / f'voz_{key}.mp3')
    (cache / f'voz_{key}.json').write_text(json.dumps([[0.2, 0.7, 'Olá'], [0.7, 1.4, 'mundo']]), encoding='utf-8')
    script = {'channel': 'T', 'fps': 25, 'subtitles': 'off', 'images': {'provider': 'none'}, 'voice': voz,
              'scenes': [{'narration': text}]}
    path = tmp_path / 'r.json'
    path.write_text(json.dumps(script), encoding='utf-8')
    done = subprocess.run([sys.executable, str(ROOT / 'main.py'), '--script', str(path), '--res', '320x180',
                           '--preset', 'ultrafast'], capture_output=True, text=True, encoding='utf-8', errors='replace')
    assert done.returncode == 0, done.stdout + done.stderr
    total = duration(tmp_path / 'output' / 'video_final.mp4')
    # entrada (0,5) + fala até ~1,4 s + folga (0,15) + saída com fade (0,55) ≈ 2,6 s.
    # Sem o corte seriam 0,5 + 2,4 + 0,55 = 3,45 s.
    assert 2.3 < total < 3.0, total
