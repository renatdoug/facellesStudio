"""Biblioteca de mídia por canal (assets/media): nomes seguros, duração e miniaturas via FFmpeg."""
from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path

from studio.util import StudioError, run

VIDEO_EXTS = {'.mp4', '.mov', '.mkv', '.webm', '.m4v', '.avi'}
MAX_BYTES = 4 * 1024 ** 3
_probe_cache: dict = {}


def safe_name(raw: str) -> str | None:
    """Nome de arquivo seguro (ASCII, sem pastas). None se a extensão não for de vídeo."""
    base = Path(raw.replace('\\', '/')).name
    stem, ext = os.path.splitext(base)
    if ext.lower() not in VIDEO_EXTS:
        return None
    ascii_stem = unicodedata.normalize('NFKD', stem).encode('ascii', 'ignore').decode()
    cleaned = re.sub(r'[^A-Za-z0-9._-]+', '_', ascii_stem).strip('._-')[:80]
    return (cleaned or 'video') + ext.lower()


def unique_name(folder: Path, name: str) -> str:
    stem, ext = os.path.splitext(name)
    candidate, n = name, 2
    while (folder / candidate).exists():
        candidate = f'{stem}-{n}{ext}'
        n += 1
    return candidate


def probe(path: Path) -> dict:
    """{'duration': segundos|None, 'video': bool} — com cache por (arquivo, data, tamanho)."""
    st = path.stat()
    key = (str(path), st.st_mtime_ns, st.st_size)
    if key not in _probe_cache:
        try:
            out = run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=codec_type',
                       '-of', 'json', path])
            data = json.loads(out)
            raw = (data.get('format') or {}).get('duration')
            _probe_cache[key] = {'duration': round(float(raw), 2) if raw else None,
                                 'video': any(s.get('codec_type') == 'video' for s in data.get('streams', []))}
        except (StudioError, ValueError, OSError):
            _probe_cache[key] = {'duration': None, 'video': False}
    return _probe_cache[key]


def thumbnail(path: Path, thumbs_dir: Path, duration: float | None) -> Path | None:
    """Quadro do vídeo em JPEG (cacheado). None se o FFmpeg não conseguir."""
    st = path.stat()
    out = thumbs_dir / f'{path.stem}_{st.st_size}_{st.st_mtime_ns // 1_000_000_000}.jpg'
    if out.exists():
        return out
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    at = min(1.0, (duration or 2) / 2)
    try:
        run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', f'{at:.2f}', '-i', path, '-frames:v', '1',
             '-vf', 'scale=320:-2', '-q:v', '4', out])
    except StudioError:
        return None
    return out if out.exists() else None
