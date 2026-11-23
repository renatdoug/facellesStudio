"""Narração por IA (edge-tts) com marcação de tempo de cada palavra, e cache em disco."""
import asyncio
import hashlib
import json
import re
import subprocess
from pathlib import Path

from .util import StudioError, run, media_duration


def _key(text, voice, rate):
    return hashlib.sha1(f'{voice}|{rate}|{text}'.encode('utf-8')).hexdigest()[:16]


async def _edge_tts(text, voice, rate, mp3_path):
    try:
        import edge_tts
    except ImportError:
        raise StudioError('Instale as dependências: pip install -r requirements.txt')
    try:  # edge-tts >= 7 só envia tempos por palavra se pedirmos
        comm = edge_tts.Communicate(text, voice, rate=rate, boundary='WordBoundary')
    except TypeError:  # versões antigas já enviavam por padrão
        comm = edge_tts.Communicate(text, voice, rate=rate)
    events = []
    with open(mp3_path, 'wb') as f:
        async for chunk in comm.stream():
            if chunk['type'] == 'audio':
                f.write(chunk['data'])
            elif chunk['type'] == 'WordBoundary':
                start = chunk['offset'] / 1e7  # unidades de 100 ns
                events.append([start, start + chunk['duration'] / 1e7, chunk['text']])
    return events


def synthesize(text, voice, rate, cache_dir, force=False):
    """Devolve (caminho_do_audio, eventos[[inicio, fim, texto]]). Reaproveita o cache
    quando texto, voz e velocidade são os mesmos."""
    cache_dir = Path(cache_dir)
    key = _key(text, voice, rate)
    mp3, meta = cache_dir / f'voz_{key}.mp3', cache_dir / f'voz_{key}.json'
    if not force and mp3.exists() and mp3.stat().st_size > 0 and meta.exists():
        return mp3, json.loads(meta.read_text(encoding='utf-8'))
    try:
        events = asyncio.run(_edge_tts(text, voice, rate, mp3))
    except StudioError:
        raise
    except Exception as err:
        mp3.unlink(missing_ok=True)
        raise StudioError(f'Falha ao gerar a narração (verifique a internet e a voz "{voice}"): {err}')
    if not mp3.exists() or mp3.stat().st_size == 0:
        raise StudioError('O edge-tts não devolveu áudio. Tente novamente em alguns minutos.')
    meta.write_text(json.dumps(events, ensure_ascii=False), encoding='utf-8')
    return mp3, events


def silent(text, cache_dir, words_per_second=2.6):
    """Modo de teste offline: silêncio com tempos de palavra simulados (ritmo de fala típico)."""
    words = text.split()
    seconds = max(2.0, len(words) / words_per_second)
    out = Path(cache_dir) / f'silencio_{_key(text, "silent", words_per_second)}.wav'
    if not out.exists():
        run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo',
             '-t', f'{seconds:.3f}', out])
    step = seconds / max(1, len(words))
    events = [[i * step, (i + 0.85) * step, wd] for i, wd in enumerate(words)]
    return out, events


def audio_seconds(path):
    return media_duration(path)


SPEECH_PAD = 0.15  # folga depois da última palavra, para não "morder" o fim da fala
_SIL_START = re.compile(r'silence_start: (-?[\d.]+)')
_SIL_END = re.compile(r'silence_end: (-?[\d.]+)')


def trailing_silence_start(path, noise_db=-45, min_len=0.3):
    """Instante em que começa o silêncio que vai até o FIM do arquivo (None se não houver).
    O silencedetect informa o fim do último silêncio quando o arquivo acaba, então "vai até o fim"
    significa: sem fim informado ou com fim igual à duração do arquivo."""
    p = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', str(path), '-af',
                        f'silencedetect=noise={noise_db}dB:d={min_len}', '-f', 'null', '-'],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    spans, current = [], None
    for line in p.stderr.splitlines():
        if (m := _SIL_START.search(line)):
            current = float(m.group(1))
        elif (m := _SIL_END.search(line)) and current is not None:
            spans.append((current, float(m.group(1))))
            current = None
    if current is not None:
        spans.append((current, None))
    if not spans:
        return None
    start, end = spans[-1]
    return start if end is None or end >= media_duration(path) - 0.06 else None


def speech_seconds(path, events, audio_dur=None, pad=SPEECH_PAD):
    """Duração útil da narração: até o fim da fala + uma folga curta.

    O edge-tts deixa ~0,9 s de silêncio depois da última palavra; contá-lo como fala criava uma pausa
    de mais de 1 s entre as cenas. O fim da fala é o MAIOR entre o fim da última palavra marcada e o
    início do silêncio final medido no áudio, então a fala nunca é cortada."""
    dur = audio_dur if audio_dur is not None else media_duration(path)
    marks = [e[1] for e in events if len(e) >= 2]
    found = [x for x in (max(marks) if marks else None, trailing_silence_start(path)) if x is not None]
    return dur if not found else min(dur, max(found) + pad)


REC_LUFS = -18.5  # volume-alvo da voz gravada: o das vozes do edge-tts (medido: -18,5 a -19,2 LUFS por cena)
LEAD_PAD = 0.12  # folga antes da primeira palavra de uma gravação (o resto do silêncio inicial é cortado)


def recorded(path, cache_dir, model=None, transcribe=None):
    """Voz GRAVADA (arquivo do usuário) no lugar do edge-tts. Devolve (wav_preparado, eventos, probabilidades, origem).

    Os tempos das palavras vêm do alinhador local (`align`), nunca do edge-tts. O áudio é preparado como o do
    edge-tts: corta o silêncio do começo (os tempos são deslocados junto), tira o ronco grave e iguala o volume
    ao das vozes sintéticas (-18,5 LUFS), para a voz gravada e as sintéticas não ficarem com volumes muito
    diferentes. O corte do silêncio do FIM é o mesmo `speech_seconds` das outras vozes. Resultado em cache."""
    from . import align
    events, probs, source = align.word_events(path, cache_dir, model or align.DEFAULT_MODEL, transcribe)
    cut = max(0.0, events[0][0] - LEAD_PAD) if events else 0.0
    out = Path(cache_dir) / f'voz_gravada_{align.file_key(path)}_{round(cut * 1000)}_n{abs(round(REC_LUFS * 10))}.wav'
    if not out.exists() or out.stat().st_size == 0:
        tmp = out.with_name(out.stem + '.part.wav')
        try:
            run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', f'{cut:.3f}', '-i', path, '-vn', '-af',
                 f'highpass=f=70,loudnorm=I={REC_LUFS}:TP=-1.5:LRA=11', '-ar', 48000, '-ac', 1, tmp])
        except StudioError as err:
            raise StudioError(f'Não consegui ler o áudio "{Path(path).name}" (formato não suportado ou arquivo corrompido): {err}')
        tmp.replace(out)
    return out, [[a - cut, b - cut, t] for a, b, t in events], probs, source
