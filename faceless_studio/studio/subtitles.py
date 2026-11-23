"""Legendas: alinhamento palavra a palavra, blocos curtos, arquivos ASS (vídeo) e SRT (YouTube)."""
import re
import unicodedata
from dataclasses import dataclass


@dataclass
class Word:
    text: str
    start: float
    end: float


def _norm(s):
    s = unicodedata.normalize('NFKD', s.lower())
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^\w]', '', s)


def align_words(narration, events, total):
    """Associa os tempos devolvidos pela voz a cada palavra do roteiro (com pontuação).
    Palavras sem correspondência recebem tempos interpolados."""
    tokens = narration.split()
    if not tokens:
        return []
    starts = [None] * len(tokens)
    ends = [None] * len(tokens)
    i = 0
    for start, end, text in events:
        nb = _norm(text)
        if not nb:
            continue
        match = None
        for j in range(i, min(len(tokens), i + 4)):  # próxima palavra (tolera até 3 puladas)
            nt = _norm(tokens[j])
            if nt and (nt.startswith(nb) or nb.startswith(nt)):
                match = j
                break
        if match is None and i > 0 and len(nb) >= 2:  # continuação de palavra composta
            prev = _norm(tokens[i - 1])
            if nb in prev and not prev.startswith(nb):
                match = i - 1
        if match is None:
            continue
        if starts[match] is None:
            starts[match] = start
        ends[match] = max(end, ends[match] or 0)
        i = match + 1  # pedaços seguintes de palavra composta caem na regra acima
    if all(s is None for s in starts):  # sem tempos: distribui pelo número de letras
        weights = [max(1, len(t)) for t in tokens]
        acc, total_w = 0.0, sum(weights)
        out = []
        for t, wgt in zip(tokens, weights):
            a = total * acc / total_w
            acc += wgt
            out.append(Word(t, a, total * acc / total_w))
        return out
    # interpola lacunas
    known = [k for k, s in enumerate(starts) if s is not None]
    for k in range(len(tokens)):
        if starts[k] is not None:
            continue
        prev = max((p for p in known if p < k), default=None)
        nxt = min((n for n in known if n > k), default=None)
        a = ends[prev] if prev is not None else 0.0
        b = starts[nxt] if nxt is not None else total
        lo = prev if prev is not None else -1
        hi = nxt if nxt is not None else len(tokens)
        span = (b - a) / (hi - lo)
        starts[k] = a + span * (k - lo - 1)
        ends[k] = starts[k] + span
    return [Word(t, s, max(e, s + 0.05)) for t, s, e in zip(tokens, starts, ends)]


LINK_WORDS = {'a', 'à', 'ao', 'as', 'às', 'o', 'os', 'e', 'é', 'de', 'da', 'do', 'das', 'dos',
              'em', 'na', 'no', 'nas', 'nos', 'um', 'uma', 'por', 'para', 'pra', 'com', 'sem',
              'que', 'se', 'ou', 'seu', 'sua', 'mais', 'muito', 'entre', 'sobre', 'como'}


def chunk_words(words, max_words=7, max_chars=38, fits=None):
    """Agrupa palavras em blocos de uma linha, preferindo quebrar após pontuação
    e sem deixar artigo/preposição pendurado no fim do bloco. `fits(texto)` (opcional) confirma
    que o bloco cabe na largura medindo a fonte de verdade."""
    chunks, cur = [], []
    for w in words:
        candidate = ' '.join(x.text for x in cur + [w])
        too_long = len(candidate) > max_chars or (fits is not None and not fits(candidate))
        if cur and (len(cur) >= max_words or too_long):
            carry = []
            while len(cur) > 2 and cur[-1].text.lower() in LINK_WORDS:
                carry.insert(0, cur.pop())
            chunks.append(cur)
            cur = carry
        cur.append(w)
        if len(cur) >= 3 and re.search(r'[.,;:!?…]$', w.text):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return chunks


def chunk_times(chunks, scene_end):
    """(início, fim) de cada bloco: aparece com a 1ª palavra e some no próximo bloco
    ou pouco depois da última palavra, se houver pausa."""
    out = []
    for n, ch in enumerate(chunks):
        a = ch[0].start
        nxt = chunks[n + 1][0].start if n + 1 < len(chunks) else scene_end
        b = min(nxt, ch[-1].end + 0.6, scene_end)
        out.append((a, max(b, a + 0.4)))
    return out


def ass_time(t):
    cs = max(0, round(t * 100))
    return f'{cs // 360000}:{(cs // 6000) % 60:02}:{(cs // 100) % 60:02}.{cs % 100:02}'


def srt_time(t):
    ms = max(0, round(t * 1000))
    return f'{ms // 3600000:02}:{(ms // 60000) % 60:02}:{(ms // 1000) % 60:02},{ms % 1000:03}'


def esc(s):
    return s.replace('\\', '\\\\').replace('{', '(').replace('}', ')').replace('\n', ' ')


def ass_color(rgb, alpha=0):
    r, g, b = rgb
    return f'&H{alpha:02X}{b:02X}{g:02X}{r:02X}'


def _karaoke_text(chunk, caps=False):
    parts = []
    for k, w in enumerate(chunk):
        nxt = chunk[k + 1].start if k + 1 < len(chunk) else w.end
        cs = max(1, round((nxt - w.start) * 100))
        parts.append(f'{{\\k{cs}}}{esc(w.text.upper() if caps else w.text)}')
    return ' '.join(parts)


CAPTION_MODES = ('karaoke', 'simple', 'pop', 'box', 'topbox', 'off')
PIL_PER_ASS = 1 / 1.16  # igual a 1/ass_helpers.ASS_SCALE: um tamanho ASS rende texto 16% mais estreito que o do Pillow
# "pop": blocos curtos e grandes que saltam na tela, palavra falada em destaque (estilo Shorts/TikTok);
# "box": o mesmo, sobre uma caixa colorida.
POP_TAGS = '{\\fscx70\\fscy70\\t(0,100,\\fscx110\\fscy110)\\t(100,200,\\fscx100\\fscy100)}'


def find_word_time(words, target, default):
    nt = _norm(target)
    for w in words:
        if nt and _norm(w.text).startswith(nt):
            return w.start
    return default


def caption_metrics(w, h, mode):
    """Tamanho da fonte, margem vertical e limites de bloco da legenda, conforme formato e estilo."""
    portrait = h > w
    big = mode in ('pop', 'box')
    if mode == 'topbox':  # frase inteira em caixa preta no topo, fora das áreas cobertas pela interface do Shorts
        fs = round(w * 0.056) if portrait else round(h * 0.05)
        margin = int(w * 0.075)
        pad = round(fs * 0.25)
        return {'fs': fs, 'margin': margin, 'margin_v': round(h * (0.115 if portrait else 0.06)), 'pad': pad,
                'avail': w - 2 * margin - 2 * pad, 'max_words': 999, 'max_chars': 999}
    if portrait:
        fs = round(w * (0.088 if big else 0.072))
        margin_v = round(h * 0.22)  # acima da faixa inferior ocupada pela interface do Shorts
    else:
        fs = round(h * (0.070 if big else 0.052))
        margin_v = round(h * (0.08 if big else 0.055))
    margin = int(w * 0.075)
    pad = round(fs * 0.26) if mode == 'box' else 0
    avail = w - 2 * margin - 2 * pad
    max_chars = max(6, int(avail / (fs * (0.72 if big else 0.62))))  # maiúsculas são mais largas
    if big:
        max_words = 3 if portrait else 4
    else:
        max_words, max_chars = 7, min(38, max_chars)
    return {'fs': fs, 'margin': margin, 'margin_v': margin_v, 'pad': pad, 'avail': avail,
            'max_words': max_words, 'max_chars': max_chars}


def write_scene_ass(path, words, callouts, scene_end, w, h, font_name, accent, mode='karaoke',
                    extra_styles=(), extra_events=(), font_path=None, callout_top=0.10):
    """Legenda da cena (modo 'karaoke', 'simple', 'pop', 'box' ou 'off'), tarjas de destaque e
    os textos animados do layout da cena (extra_styles/extra_events). `callout_top` é a altura (fração da tela)
    em que as tarjas ficam: 0,10 nas cenas de imagem/vídeo; mais baixo nas que têm o nome do canal no canto."""
    if mode not in CAPTION_MODES:
        raise ValueError(f'Modo de legenda inválido: {mode}')
    m = caption_metrics(w, h, mode)
    fs, margin = m['fs'], m['margin']
    white = ass_color((255, 255, 255))
    dark = ass_color((8, 20, 34))
    if mode in ('karaoke', 'pop'):  # palavra falada fica na cor de destaque
        primary, secondary = ass_color(accent), white
    elif mode == 'box':
        primary, secondary = dark, dark
    else:
        primary, secondary = white, white
    outline = ass_color((10, 14, 22))
    shadow = ass_color((0, 0, 0), 0x70)
    co_fs = round(h * 0.046)
    co_box = ass_color(accent)
    co_text = ass_color((8, 20, 34))
    if mode == 'topbox':  # alinhamento 8 (topo), caixa preta opaca, texto branco
        sub_style = (f'Style: Sub,{font_name},{fs},&H00FFFFFF,&H00FFFFFF,&H00000000,{shadow},-1,0,0,0,100,100,0,0,3,'
                     f'{m["pad"]},0,8,{margin},{margin},{m["margin_v"]},1')
    elif mode == 'box':  # BorderStyle 3: caixa opaca na cor do contorno
        sub_style = (f'Style: Sub,{font_name},{fs},{primary},{secondary},{co_box},{shadow},-1,0,0,0,100,100,0,0,3,'
                     f'{m["pad"]},0,2,{margin},{margin},{m["margin_v"]},1')
    else:
        thick = max(3, round(fs * 0.07)) if mode == 'pop' else max(2, round(h / 300))
        sub_style = (f'Style: Sub,{font_name},{fs},{primary},{secondary},{outline},{shadow},-1,0,0,0,100,100,0,0,1,'
                     f'{thick},{max(1, round(h / 540))},2,{margin},{margin},{m["margin_v"]},1')
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{sub_style}
Style: Callout,{font_name},{co_fs},{co_text},{co_text},{co_box},{shadow},-1,0,0,0,100,100,1,0,3,{round(h * 0.014)},0,9,{margin},{margin},{round(h * callout_top)},1
{''.join(st + chr(10) for st in extra_styles)}
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = list(extra_events)
    if mode == 'topbox' and words:
        from .visuals import wrap_lines
        text = ' '.join(x.text for x in words)
        lines = wrap_lines(text, font_path, round(fs * PIL_PER_ASS), m['avail']) if font_path is not None else [text]
        body = '\\N'.join(esc(ln) for ln in lines)
        events.append(f'Dialogue: 0,{ass_time(max(0.0, words[0].start - 0.05))},{ass_time(scene_end)},Sub,,0,0,0,,{body}')
    elif mode != 'off' and words:
        fits, width = None, None
        if font_path is not None:  # mede a largura de verdade, com a fonte do vídeo
            from .visuals import text_width
            caps = mode in ('pop', 'box')

            def width(t):
                return text_width(t.upper() if caps else t, font_path, round(fs * PIL_PER_ASS))

            def fits(t):
                return width(t) <= m['avail']
        chunks = chunk_words(words, max_words=m['max_words'], max_chars=m['max_chars'], fits=fits)
        for ch, (a, b) in zip(chunks, chunk_times(chunks, scene_end)):
            size_tag = ''
            if width is not None:  # uma palavra sozinha mais larga que a tela: encolhe só este bloco
                wide = width(' '.join(x.text for x in ch))
                if wide > m['avail']:
                    size_tag = f'{{\\fs{int(fs * m["avail"] / wide)}}}'
            if mode == 'karaoke':
                text = _karaoke_text(ch)
            elif mode == 'pop':
                text = POP_TAGS + _karaoke_text(ch, caps=True)
            elif mode == 'box':
                text = POP_TAGS + esc(' '.join(x.text for x in ch).upper())
            else:
                text = esc(' '.join(x.text for x in ch))
            events.append(f'Dialogue: 0,{ass_time(a)},{ass_time(b)},Sub,,0,0,0,,{size_tag}{text}')
    for co in callouts or []:
        text = co.get('text', '').strip()
        if not text:
            continue
        if 'at' in co:
            a = float(co['at'])
        else:
            a = find_word_time(words, co.get('on_word', ''), 0.6)
        b = float(co['until']) if 'until' in co else scene_end - 0.15
        pop = '{\\fad(150,200)\\fscx80\\fscy80\\t(0,180,\\fscx100\\fscy100)}'
        events.append(f'Dialogue: 1,{ass_time(a)},{ass_time(max(b, a + 0.5))},Callout,,0,0,0,,{pop}{esc(text)}')
    path.write_text(header + '\n'.join(events) + '\n', encoding='utf-8')


def srt_blocks(words, offset):
    """Blocos SRT (texto simples) da cena, deslocados para o tempo global do vídeo."""
    chunks = chunk_words(words)
    end = words[-1].end + 0.6 if words else 0
    for ch, (a, b) in zip(chunks, chunk_times(chunks, end)):
        yield a + offset, b + offset, ' '.join(x.text for x in ch)


def write_srt(path, blocks):
    lines = []
    for n, (a, b, text) in enumerate(blocks, 1):
        lines += [str(n), f'{srt_time(a)} --> {srt_time(b)}', text, '']
    path.write_text('\n'.join(lines), encoding='utf-8')
