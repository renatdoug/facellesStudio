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


def chunk_words(words, max_words=7, max_chars=38):
    """Agrupa palavras em blocos de uma linha, preferindo quebrar após pontuação
    e sem deixar artigo/preposição pendurado no fim do bloco."""
    chunks, cur = [], []
    for w in words:
        candidate = ' '.join(x.text for x in cur + [w])
        if cur and (len(cur) >= max_words or len(candidate) > max_chars):
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


def _karaoke_text(chunk):
    parts = []
    for k, w in enumerate(chunk):
        nxt = chunk[k + 1].start if k + 1 < len(chunk) else w.end
        cs = max(1, round((nxt - w.start) * 100))
        parts.append(f'{{\\k{cs}}}{esc(w.text)}')
    return ' '.join(parts)


def find_word_time(words, target, default):
    nt = _norm(target)
    for w in words:
        if nt and _norm(w.text).startswith(nt):
            return w.start
    return default


def write_scene_ass(path, words, callouts, scene_end, w, h, font_name, accent, mode='karaoke',
                    extra_styles=(), extra_events=()):
    """Legenda da cena (modo 'karaoke', 'simple' ou 'off'), tarjas de destaque e
    os textos animados do layout da cena (extra_styles/extra_events)."""
    fs = round(h * 0.052)
    white = ass_color((255, 255, 255))
    if mode == 'karaoke':  # palavra falada fica na cor de destaque
        primary, secondary = ass_color(accent), white
    else:
        primary, secondary = white, white
    outline = ass_color((10, 14, 22))
    shadow = ass_color((0, 0, 0), 0x70)
    co_fs = round(h * 0.046)
    co_box = ass_color(accent)
    co_text = ass_color((8, 20, 34))
    margin = int(w * 0.075)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{font_name},{fs},{primary},{secondary},{outline},{shadow},-1,0,0,0,100,100,0,0,1,{max(2, round(h / 300))},{max(1, round(h / 540))},2,{margin},{margin},{round(h * 0.055)},1
Style: Callout,{font_name},{co_fs},{co_text},{co_text},{co_box},{shadow},-1,0,0,0,100,100,1,0,3,{round(h * 0.014)},0,9,{margin},{margin},{round(h * 0.10)},1
{''.join(st + chr(10) for st in extra_styles)}
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = list(extra_events)
    if mode != 'off' and words:
        chunks = chunk_words(words)
        for ch, (a, b) in zip(chunks, chunk_times(chunks, scene_end)):
            text = _karaoke_text(ch) if mode == 'karaoke' else esc(' '.join(x.text for x in ch))
            events.append(f'Dialogue: 0,{ass_time(a)},{ass_time(b)},Sub,,0,0,0,,{text}')
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
