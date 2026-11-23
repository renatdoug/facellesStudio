"""Roteiro em TEXTO SIMPLES -> roteiro JSON do Faceless Studio (sem IA e sem custo).

Você cola a narração; o programa divide em cenas e monta o JSON:
  - uma linha em branco separa cenas (parágrafo = cena). Se o texto não tem parágrafos, ou se um parágrafo é
    longo demais, ele é dividido em frases e as frases são agrupadas até o tamanho de cena escolhido;
  - `Título: ...` (ou `# ...`) na primeira linha define o título do vídeo;
  - linhas que começam com `Fonte:`, `Fontes:` ou `Referências:` NÃO são narradas: vão para o campo `fontes`;
  - cada cena vira imagem (o `prompt` parte do próprio texto da cena; refine no editor) ou, sem imagens, um cartão.
A divisão é só por regras de pontuação: o programa não "entende" o texto. Revise as cenas no editor.

DIÁLOGO (cartum): se o texto tem falas no formato `Nome: fala` entre DOIS personagens, vira um vídeo de bonecos
animados. Opcionalmente, `Nome (brava): fala` define a emoção e `[aponta]`, `[close]`... definem gesto e câmera.
"""
from __future__ import annotations

import re

FORMATS = {'vertical': '1080x1920', 'horizontal': '1920x1080', 'square': '1080x1080'}
SCENE_WORDS = {'curta': 14, 'media': 24, 'longa': 45}
DEFAULT_SCENE_SIZE = {'vertical': 'curta', 'square': 'curta', 'horizontal': 'longa'}
PROVIDERS = ('gemini', 'pollinations', 'openai', 'comfyui', 'none')
DEFAULT_VOICE = 'pt-BR-FranciscaNeural'
STYLE = ('editorial digital illustration, clean flat shapes, soft cinematic lighting, dark navy and teal palette, '
         'no identifiable faces, screens show only abstract waveforms with no digits')
FULL_BLEED = ('tall vertical full-bleed composition that fills the entire frame edge to edge, '
              'no empty margins or flat bands')
ABBREV = {'dr', 'dra', 'sr', 'sra', 'srs', 'prof', 'profa', 'vs', 'etc', 'ex', 'fig', 'cap', 'art', 'ed', 'pag', 'pág',
          'al', 'nº', 'no', 'obs', 'cf', 'ref', 'tab', 'vol', 'p', 'pp', 'ca', 'aprox', 'min', 'máx', 'máx.'}
_SENT_SPLIT = re.compile(r'(?<=[.!?…])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇÀ0-9"“(¿¡\[])')
_SOURCE_HEAD = re.compile(r'^\s*(fontes?|refer[êe]ncias?|bibliografia)\s*:', re.IGNORECASE)
_TITLE_LINE = re.compile(r'^\s*(?:t[íi]tulo\s*:|#\s+)\s*(.+?)\s*$', re.IGNORECASE)


def _words(text):
    return len(text.split())


def split_sentences(paragraph: str) -> list[str]:
    """Divide em frases pela pontuação, sem separar abreviações ("Dr. Silva", "etc.", "p. ex.") nem iniciais."""
    parts = [p.strip() for p in _SENT_SPLIT.split(paragraph.strip()) if p.strip()]
    merged: list[str] = []
    for part in parts:
        if merged:
            last_word = merged[-1].split()[-1].rstrip('.').lower().lstrip('(')
            if merged[-1].endswith('.') and (last_word in ABBREV or (len(last_word) == 1 and last_word.isalpha())):
                merged[-1] = f'{merged[-1]} {part}'
                continue
        merged.append(part)
    return merged


def group_sentences(sentences: list[str], max_words: int) -> list[str]:
    """Junta frases consecutivas até `max_words` palavras por cena. Uma frase maior que o limite fica sozinha."""
    groups: list[list[str]] = []
    for sentence in sentences:
        if groups and _words(' '.join(groups[-1])) + _words(sentence) <= max_words:
            groups[-1].append(sentence)
        else:
            groups.append([sentence])
    return [' '.join(g) for g in groups]


def split_scenes(body: str, max_words: int) -> list[str]:
    """Texto -> narrações das cenas: parágrafos viram cenas; parágrafos longos (ou texto sem parágrafos) são
    divididos por frases e reagrupados."""
    paragraphs = [re.sub(r'\s+', ' ', p).strip() for p in re.split(r'\n\s*\n', body) if p.strip()]
    scenes: list[str] = []
    if len(paragraphs) == 1:  # sem parágrafos: tudo é decidido pelas frases
        return group_sentences(split_sentences(paragraphs[0]), max_words)
    for paragraph in paragraphs:
        if _words(paragraph) <= max_words:
            scenes.append(paragraph)
        else:
            scenes.extend(group_sentences(split_sentences(paragraph), max_words))
    return scenes


def extract_parts(text: str) -> tuple[str | None, str, list[str]]:
    """(título, corpo da narração, fontes). Tira `Título:`/`# ` da 1ª linha e os parágrafos de Fonte/Referências."""
    lines = text.replace('\r\n', '\n').replace('\r', '\n').strip('\n ﻿').split('\n')
    title = None
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and (m := _TITLE_LINE.match(lines[0])):
        title = m.group(1)
        lines.pop(0)
    kept: list[str] = []
    fontes: list[str] = []
    for block in re.split(r'\n\s*\n', '\n'.join(lines)):
        block_lines = [ln for ln in block.split('\n') if ln.strip()]
        if block_lines and _SOURCE_HEAD.match(block_lines[0]):
            first = _SOURCE_HEAD.sub('', block_lines[0], count=1).strip()
            fontes += [x.strip(' -•\t') for x in ([first] if first else []) + block_lines[1:] if x.strip(' -•\t')]
        elif block.strip():
            kept.append(block)
    return title, '\n\n'.join(kept), fontes


def short_title(text: str, n: int = 5) -> str:
    words = re.sub(r'[^\w\s%-]', '', text, flags=re.UNICODE).split()[:n]
    return ' '.join(words) if words else 'Cena'


_RESERVED_NAMES = {'titulo', 'título', 'fonte', 'fontes', 'referencia', 'referência', 'referencias', 'referências',
                   'nota', 'notas', 'obs', 'observação', 'observacao', 'bibliografia'}
_SPEAKER_LINE = re.compile(r'^\s*([^\W\d_][\w .\-]{0,22}?)\s*(?:\(([^)]{1,24})\))?((?:\s*\[[^\]]{1,30}\])*)\s*:\s*(\S.*?)\s*$', re.UNICODE)
_BRACKET = re.compile(r'\[([^\]]{1,30})\]')
EMOTION_WORDS = {
    'neutral': ('neutra', 'neutro', 'normal', 'calma', 'calmo'),
    'happy': ('feliz', 'alegre', 'animada', 'animado', 'rindo', 'contente', 'empolgada', 'empolgado'),
    'angry': ('brava', 'bravo', 'irritada', 'irritado', 'nervosa', 'nervoso', 'raiva', 'furiosa', 'furioso'),
    'sad': ('triste', 'chateada', 'chateado', 'desanimada', 'desanimado'),
    'surprised': ('surpresa', 'surpreso', 'espantada', 'espantado', 'chocada', 'chocado', 'assustada', 'assustado'),
    'thinking': ('pensativa', 'pensativo', 'pensando', 'duvida', 'dúvida', 'desconfiada', 'desconfiado', 'curiosa', 'curioso'),
    'smug': ('convencida', 'convencido', 'esnobe', 'irônica', 'ironica', 'irônico', 'ironico', 'confiante', 'sabichona', 'sabichão'),
}
GESTURE_WORDS = {'point': ('aponta', 'apontando', 'apontar'), 'hip': ('mãos na cintura', 'maos na cintura', 'cintura'),
                 'open': ('abre os braços', 'abre os bracos', 'explica', 'braços abertos'),
                 'shrug': ('dá de ombros', 'da de ombros', 'ombros')}
CAMERA_WORDS = {'wide': ('plano aberto', 'aberto', 'wide'), 'speaker': ('close', 'zoom', 'plano fechado')}
MAX_DIALOGUE_WORDS = 22


def _name_key(name: str) -> str:
    return re.sub(r'\s+', ' ', name.strip()).lower()


def _speaker_slug(name: str) -> str:
    import unicodedata
    ascii_name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '_', ascii_name).strip('_') or 'personagem'


def parse_dialogue(body: str) -> list[dict] | None:
    """Falas `Nome: texto` do corpo, ou None se o texto não parece um diálogo. Linhas sem `Nome:` continuam a fala
    anterior. Reconhece diálogo quando há exatamente DOIS nomes, ao menos 3 falas e a maioria das linhas é fala."""
    lines = [ln for ln in body.replace('\r', '').split('\n') if ln.strip()]
    entries: list[dict] = []
    for ln in lines:
        m = _SPEAKER_LINE.match(ln)
        if m and _name_key(m.group(1)) not in _RESERVED_NAMES and len(m.group(1).split()) <= 3:
            entries.append({'name': re.sub(r'\s+', ' ', m.group(1).strip()), 'tag': (m.group(2) or '').strip(),
                            'text': f'{m.group(3) or ""} {m.group(4)}'.strip()})
        elif entries:
            entries[-1]['text'] += ' ' + ln.strip()
        else:
            return None
    names = {_name_key(e['name']) for e in entries}
    if len(names) != 2 or len(entries) < 3 or len(entries) < 0.7 * len(lines):
        return None
    return entries


def _find_word(table: dict, token: str) -> str | None:
    t = token.strip().lower()
    return next((key for key, words in table.items() if t in words), None)


def _auto_emotion(text: str) -> str:
    end = text.rstrip().rstrip('"”)')
    if end.endswith(('?!', '!?')):
        return 'surprised'
    if end.endswith('!'):
        return 'happy'
    if end.endswith('?'):
        return 'thinking'
    return 'neutral'


def dialogue_from_text(text: str, options: dict | None = None) -> tuple[dict, list[str]] | None:
    """Roteiro de CARTUM a partir de falas `Nome: fala`; None se o texto não for um diálogo."""
    opts = dict(options or {})
    title_in_text, body, fontes = extract_parts(text)
    entries = parse_dialogue(body)
    if entries is None:
        return None
    fmt = opts.get('format') if opts.get('format') in FORMATS else 'vertical'
    FEM, MASC = DEFAULT_VOICE, 'pt-BR-AntonioNeural'
    # No diálogo a voz de cada personagem sai do NOME (terminado em "a" = feminina), sem repetir a mesma voz nos dois.
    # Só "dialogue_voices": [voz1, voz2] muda isso (a opção "voice" é da narração e não vale aqui).
    picked = [v if isinstance(v, str) and re.fullmatch(r'[a-z]{2}-[A-Z]{2}-[A-Za-z]+Neural', v) else None
              for v in (list(opts.get('dialogue_voices') or []) + [None, None])[:2]]
    chars, order, notes = {}, [], []
    for e in entries:
        key = _name_key(e['name'])
        if key not in order:
            order.append(key)
            cid = _speaker_slug(e['name'])
            guess = FEM if key.endswith('a') else MASC
            if len(order) == 2 and chars and guess == next(iter(chars.values()))['voice']:
                guess = MASC if guess == FEM else FEM
            chars[cid] = {'name': e['name'], 'voice': picked[len(order) - 1] or guess}
        e['cid'] = _speaker_slug(e['name'])
    scenes = []
    for e in entries:
        speech = e['text']
        gesture, camera, emotion = 'none', 'auto', _find_word(EMOTION_WORDS, e['tag']) if e['tag'] else None
        if e['tag'] and emotion is None:
            notes.append(f'Emoção desconhecida "{e["tag"]}" na fala de {e["name"]}: usei a automática.')
        for token in _BRACKET.findall(speech):
            gesture = _find_word(GESTURE_WORDS, token) or gesture
            camera = _find_word(CAMERA_WORDS, token) or camera
        speech = re.sub(r'\s+', ' ', _BRACKET.sub('', speech)).strip()
        if not speech:
            continue
        pieces = group_sentences(split_sentences(speech), MAX_DIALOGUE_WORDS) if _words(speech) > MAX_DIALOGUE_WORDS else [speech]
        for k, piece in enumerate(pieces):
            scene = {'id': f'fala{len(scenes) + 1}', 'speaker': e['cid'], 'narration': piece,
                     'emotion': emotion or _auto_emotion(piece)}
            if gesture != 'none' and k == 0:
                scene['gesture'] = gesture
            if camera != 'auto' and k == 0:
                scene['camera'] = camera
            scenes.append(scene)
    title = (str(opts.get('title') or '').strip() or title_in_text or short_title(scenes[0]['narration'], 6)).strip()
    data = {'title': title, 'channel': str(opts.get('channel') or ''), 'theme': 'geek', 'resolution': FORMATS[fmt],
            'fps': 30, 'subtitles': 'topbox', 'default_transition': 'cut', 'pause': 0.15,
            'images': {'provider': 'none', 'style': STYLE},
            'toon': {'background': 'room', 'characters': chars}, 'scenes': scenes}
    if fontes:
        data['fontes'] = fontes
    names = ' e '.join(c['name'] for c in chars.values())
    notes.append('Vozes: ' + ', '.join(f'{c["name"]} → {c["voice"].split("-")[2].replace("Neural", "")}' for c in chars.values())
                 + ' (palpite pelo nome; troque em "toon.characters" se quiser).')
    total = sum(_words(s['narration']) for s in scenes)
    notes.insert(0, f'Diálogo entre {names}: {len(entries)} falas em {len(scenes)} cenas de bonecos animados '
                    f'({total} palavras, ≈ {total / 2.5:.0f} s).')
    if fontes:
        notes.append(f'{len(fontes)} linha(s) de fonte/referência não serão narradas: guardei em "fontes".')
    return data, notes


def script_from_text(text: str, options: dict | None = None) -> tuple[dict, list[str]]:
    """Devolve (roteiro, notas). Levanta ValueError se não houver texto para narrar.
    Texto com falas `Nome: fala` entre dois personagens vira cartum; o resto vira narração em cenas."""
    dialogue = dialogue_from_text(text, options)
    if dialogue is not None:
        return dialogue
    opts = dict(options or {})
    fmt = opts.get('format') if opts.get('format') in FORMATS else 'vertical'
    size = opts.get('scene_size') if opts.get('scene_size') in SCENE_WORDS else DEFAULT_SCENE_SIZE[fmt]
    provider = opts.get('provider') if opts.get('provider') in PROVIDERS else 'gemini'
    with_images = opts.get('images', 'todas') != 'nenhuma' and provider != 'none'
    voice = str(opts.get('voice') or DEFAULT_VOICE)
    if not re.fullmatch(r'[a-z]{2}-[A-Z]{2}-[A-Za-z]+Neural', voice):
        voice = DEFAULT_VOICE
    title_in_text, body, fontes = extract_parts(text)
    if not body.strip():
        raise ValueError('Não encontrei texto para narrar.')
    narrations = split_scenes(body, SCENE_WORDS[size])
    vertical = fmt != 'horizontal'
    title = (str(opts.get('title') or '').strip() or title_in_text or short_title(narrations[0], 6)).strip()
    style = str(opts.get('style') or '').strip() or (f'{STYLE}, {FULL_BLEED}' if vertical else STYLE)
    scenes = []
    for n, narration in enumerate(narrations, 1):
        scene = {'id': f'cena{n}', 'title': short_title(narration), 'narration': narration}
        if with_images:
            scene['prompt'] = f'Illustration that visually represents this idea: {narration}'
        else:
            scene['headline'] = short_title(narration, 6).upper()
        scenes.append(scene)
    data = {'title': title, 'channel': str(opts.get('channel') or ''), 'theme': 'health', 'resolution': FORMATS[fmt],
            'fps': 30, 'voice': voice, 'subtitles': 'pop' if vertical else 'karaoke',
            'default_transition': 'punch' if vertical else 'cut', 'pause': 0.2,
            'images': {'provider': provider, 'style': style, 'seed': 1234}, 'scenes': scenes}
    if fontes:
        data['fontes'] = fontes
    total = sum(_words(s) for s in narrations)
    notes = [f'Texto simples: dividi em {len(scenes)} cenas ({total} palavras, ≈ {total / 2.5:.0f} s de narração).']
    if fontes:
        notes.append(f'{len(fontes)} linha(s) de fonte/referência não serão narradas: guardei em "fontes".')
    return data, notes
