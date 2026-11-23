"""Importação de roteiros escritos por IA (Claude, ChatGPT, Gemini...): extrai o JSON do texto colado,
valida com o MESMO validador do motor (`main.validate_script`) e cria um projeto novo sem sobrescrever nada."""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import main as engine
from studio import layouts, script_check, text_script
from studio.util import StudioError

MAX_CHARS = 2_000_000
WORDS_PER_SECOND = 2.5
_FENCE = re.compile(r'```(?:json|JSON)?\s*(\{.*?\})\s*```', re.DOTALL)
_SCENE_REF = re.compile(r'[Cc]ena (\d+)')
FORMATS = {'1920x1080': 'Horizontal 16:9', '1080x1920': 'Vertical 9:16', '1080x1080': 'Quadrado 1:1'}


def extract_json(text: str) -> tuple[str, list[str]]:
    """Pega o objeto JSON do texto colado. Aceita bloco ```json e texto antes/depois (comum em chats)."""
    raw = text.lstrip('﻿').strip()
    if raw.startswith('{') and raw.endswith('}'):
        return raw, []
    m = _FENCE.search(raw)
    if m:
        return m.group(1), ['Removi o texto fora do bloco de código do JSON.']
    start, end = raw.find('{'), raw.rfind('}')
    if start != -1 and end > start:
        return raw[start:end + 1], ['Removi o texto antes/depois do JSON.']
    return raw, []


def _json_error(text: str, err: json.JSONDecodeError) -> str:
    line = text.splitlines()[err.lineno - 1] if 0 < err.lineno <= len(text.splitlines()) else ''
    snippet = line.strip()[:90]
    hints = []
    if any(c in text for c in '“”‘’'):
        hints.append('O texto tem aspas curvas (“ ”); o JSON exige aspas retas (").')
    if re.search(r',\s*[}\]]', text):
        hints.append('Há uma vírgula sobrando antes de } ou ].')
    if re.search(r'^\s*//', text, re.MULTILINE) or '/*' in text:
        hints.append('JSON não aceita comentários (// ou /* */).')
    tip = ' ' + ' '.join(hints) if hints else ' Peça à IA: "devolva só o JSON válido, sem comentários".'
    where = f' Perto de: {snippet}' if snippet else ''
    return f'JSON inválido (linha {err.lineno}, coluna {err.colno}): {err.msg}.{where}{tip}'


def looks_like_json(text: str) -> bool:
    """JSON (de uma IA) começa com { ou vem num bloco ```json; qualquer outra coisa é roteiro em texto simples."""
    raw = text.lstrip('\ufeff').lstrip()
    return raw.startswith('{') or bool(_FENCE.search(raw))


def analyze(text: str, project_dir: Path | None = None, options: dict | None = None) -> dict:
    """Lê o texto colado (roteiro em texto simples OU JSON) e devolve {ok, error, notes, summary, issues, data}.
    Nunca grava nada. `options` só vale para texto simples (formato, imagens, voz...; ver studio/text_script.py)."""
    result = {'ok': False, 'error': None, 'notes': [], 'summary': None, 'issues': [], 'data': None, 'mode': 'json'}
    if not text or not text.strip():
        result['error'] = {'message': 'Cole o roteiro (texto simples) ou o JSON gerado por uma IA.', 'scene': None}
        return result
    if len(text) > MAX_CHARS:
        result['error'] = {'message': 'Texto grande demais para ser um roteiro.', 'scene': None}
        return result
    if looks_like_json(text):
        body, notes = extract_json(text)
        result['notes'] = notes
        try:
            data = json.loads(body)
        except json.JSONDecodeError as err:
            result['error'] = {'message': _json_error(body, err), 'scene': None}
            return result
        if not isinstance(data, dict):
            result['error'] = {'message': 'O roteiro precisa ser um objeto JSON, começando com { e terminando com }.',
                               'scene': None}
            return result
    else:
        result['mode'] = 'texto'
        try:
            data, result['notes'] = text_script.script_from_text(text, options)
        except ValueError as err:
            result['error'] = {'message': str(err), 'scene': None}
            return result
    try:
        engine.validate_script(data)  # o mesmo validador do motor e do editor
    except StudioError as err:
        m = _SCENE_REF.search(str(err))
        result['error'] = {'message': str(err), 'scene': int(m.group(1)) if m else None}
        return result
    result['data'] = data
    result['issues'] = script_check.check(data, project_dir)
    result['summary'] = _summary(data)
    result['ok'] = True
    return result


# Custo medido pelo Renato em 22/11/2026: 3 imagens 2K do Gemini = R$ 1,87 (≈ R$ 0,62 cada), igual em 16:9 e 9:16.
# É uma estimativa para ele decidir antes de gerar; o preço do Google pode mudar.
GEMINI_IMAGE_BRL = 0.62


def _summary(data: dict) -> dict:
    scenes = []
    total = 0.0
    to_generate = 0
    for n, s in enumerate(data['scenes'], 1):
        words = len(str(s.get('narration', '')).split())
        seconds = round(words / WORDS_PER_SECOND + 0.8, 1)
        total += seconds
        layout = layouts.detect_layout(s)
        if layout == 'image' and not s.get('image') and str(s.get('prompt') or '').strip():
            to_generate += 1
        notes = s.get('revisar') if isinstance(s.get('revisar'), list) else []
        scenes.append({'index': n, 'id': str(s.get('id') or f'{n:02}'), 'title': s.get('title') or s.get('headline') or '',
                       'layout': layout, 'words': words, 'seconds': seconds, 'revisar': len(notes)})
    res = str(data.get('resolution', '1920x1080')).lower()
    provider = (data.get('images') or {}).get('provider', 'pollinations')
    return {'title': data.get('title') or '', 'channel': data.get('channel') or '', 'resolution': res,
            'format': FORMATS.get(res, res), 'subtitles': data.get('subtitles', 'karaoke'),
            'voice': data.get('voice', 'pt-BR-AntonioNeural'), 'scenes': scenes, 'seconds': round(total, 1),
            'images': to_generate, 'provider': provider,
            'cost_brl': round(to_generate * GEMINI_IMAGE_BRL, 2) if provider == 'gemini' and to_generate else None}


def slugify(text: str, fallback: str = 'roteiro-importado') -> str:
    ascii_text = unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode().lower()
    slug = re.sub(r'[^a-z0-9]+', '-', ascii_text).strip('-')[:50].strip('-')
    return slug or fallback


def write_new(folder: Path, data: dict, wanted: str | None) -> str:
    """Grava o roteiro como arquivo NOVO na pasta do canal: se o nome já existe, acrescenta -2, -3...
    (criação exclusiva: nunca sobrescreve, nem em corrida entre duas importações)."""
    base = slugify(wanted or data.get('title') or '')
    payload = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    for n in range(1, 1000):
        name = f'{base}.json' if n == 1 else f'{base}-{n}.json'
        try:
            with (folder / name).open('x', encoding='utf-8') as fh:
                fh.write(payload)
            return name
        except FileExistsError:
            continue
    raise StudioError('Não consegui achar um nome livre para o roteiro.')
