"""Narração por IA (edge-tts) com marcação de tempo de cada palavra, e cache em disco."""
import asyncio
import hashlib
import json
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
