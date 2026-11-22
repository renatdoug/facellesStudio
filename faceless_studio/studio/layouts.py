"""Layouts de cena conforme o conteúdo: card, image, list, number, compare, quote, chart.

Cada layout produz:
  - a imagem de fundo (que recebe o movimento de câmera);
  - estilos e eventos ASS com os textos animados (ficam parados e nítidos sobre o fundo,
    surgindo no momento em que a narração fala de cada item).
"""
from PIL import ImageDraw, ImageFont

from . import charts, visuals
from .subtitles import ass_color, ass_time, esc, find_word_time
from .util import StudioError

LAYOUTS = ('card', 'image', 'video', 'list', 'number', 'compare', 'quote', 'chart')
TEXT_LAYOUTS = ('list', 'number', 'compare', 'quote', 'chart')


def detect_layout(scene):
    if scene.get('layout'):
        if scene['layout'] not in LAYOUTS:
            raise StudioError(f'Layout "{scene["layout"]}" inválido. Use: ' + ', '.join(LAYOUTS))
        return scene['layout']
    if scene.get('video'):  # clipe do usuário (ou, no futuro, gerado por IA) como fundo
        return 'video'
    if scene.get('image') or scene.get('prompt'):
        return 'image'
    for key, name in (('chart', 'chart'), ('number', 'number'), ('items', 'list'),
                      ('compare', 'compare'), ('quote', 'quote')):
        if scene.get(key):
            return name
    return 'card'


class Ctx:
    """Tudo que um layout precisa saber sobre a cena."""

    def __init__(self, scene, idx, w, h, theme, channel, fonts, font_name, words, speech_start,
                 speech_end, scene_end):
        self.scene, self.idx, self.w, self.h = scene, idx, w, h
        self.theme, self.channel, self.fonts, self.font_name = theme, channel, fonts, font_name
        self.pal = visuals.palette(theme)
        self.words, self.speech_start, self.speech_end, self.scene_end = words, speech_start, speech_end, scene_end
        self.pad = int(w * 0.075)

    def t(self, n, total, on_word=None, at=None):
        """Momento de entrada do item n de `total`: palavra-gatilho, tempo fixo ou distribuído."""
        if at is not None:
            return float(at)
        span = (self.speech_end - self.speech_start) * 0.85
        default = self.speech_start + 0.3 + span * n / max(1, total)
        return find_word_time(self.words, on_word, default) if on_word else default


ASS_SCALE = 1.16  # no ASS o tamanho inclui ascendente+descendente; isto iguala ao tamanho do Pillow


def _style(name, font, size, color, bold=False, box=None, align=7, outline=0, shadow=0):
    """Linha de estilo ASS. box=(cor, padding) desenha caixa opaca atrás do texto.
    `size` é o tamanho no Pillow (o mesmo usado para medir e quebrar as linhas)."""
    prim = ass_color(color)
    size = round(size * ASS_SCALE)
    if box:
        return (f'Style: {name},{font},{size},{prim},{prim},{ass_color(box[0])},&H80000000,'
                f'{-1 if bold else 0},0,0,0,100,100,0,0,3,{box[1]},0,{align},0,0,0,1')
    return (f'Style: {name},{font},{size},{prim},{prim},&H00101418,&H90000000,'
            f'{-1 if bold else 0},0,0,0,100,100,0,0,1,{outline},{shadow},{align},0,0,0,1')


def _ev(start, end, style, text, layer=2):
    return f'Dialogue: {layer},{ass_time(start)},{ass_time(max(end, start + 0.2))},{style},,0,0,0,,{text}'


def _headline_events(c, y_frac=0.19, size_frac=0.072, max_lines=2):
    head = c.scene.get('headline') or c.scene.get('title') or ''
    if not head:
        return [], [], y_frac
    size = round(c.h * size_frac)
    # com tarjas (canto superior direito), o título deixa espaço livre à direita
    max_w = c.w - 2 * c.pad - (int(c.w * 0.24) if c.scene.get('callouts') else 0)
    lines = visuals.wrap_lines(head, c.fonts['bold'], size, max_w)
    while len(lines) > max_lines and size > 24:
        size -= 2
        lines = visuals.wrap_lines(head, c.fonts['bold'], size, max_w)
    y = int(c.h * y_frac)
    text = '\\N'.join(esc(x) for x in lines[:max_lines])
    ev = [_ev(0, c.scene_end, 'LHead', f'{{\\pos({c.pad},{y})\\fad(300,0)}}{text}')]
    bar_y = y + int(size * 1.22 * min(len(lines), max_lines)) + int(c.h * 0.012)
    bar = (f'{{\\pos({c.pad},{bar_y})\\p1\\fad(300,0)\\c{ass_color(c.pal["accent"])}}}'
           f'm 0 0 l {int(c.w * 0.09)} 0 {int(c.w * 0.09)} {max(4, c.h // 135)} 0 {max(4, c.h // 135)}{{\\p0}}')
    ev.append(_ev(0, c.scene_end, 'LShape', bar))
    styles = [_style('LHead', c.font_name, size, (255, 255, 255), bold=True, outline=0, shadow=0),
              _style('LShape', c.font_name, 10, c.pal['accent'])]
    return styles, ev, (bar_y + c.h * 0.05) / c.h


# ---------------------------------------------------------------- layouts

def layout_list(c, bg_path):
    visuals.base_background(c.w, c.h, c.theme, c.channel, c.idx, c.fonts, waves=False).save(bg_path)
    styles, events, top = _headline_events(c)
    items = c.scene.get('items') or []
    if not items:
        raise StudioError(f'Cena {c.idx}: layout "list" precisa de "items".')
    items = [it if isinstance(it, dict) else {'text': str(it)} for it in items]
    n = len(items)
    area_top, area_bottom = max(top, 0.34) * c.h, 0.80 * c.h
    step = min(c.h * 0.095, (area_bottom - area_top) / n)
    fs = round(min(c.h * 0.048, step * 0.62))
    key_fs = fs
    key_w = max(visuals.text_width(it.get('key', ''), c.fonts['bold'], key_fs) for it in items)
    has_keys = any(it.get('key') for it in items)
    x_key = c.pad
    x_text = c.pad + (int(key_w + c.h * 0.05) if has_keys else int(fs * 1.4))
    styles += [_style('LItem', c.font_name, fs, (255, 255, 255), bold=False, align=4),
               _style('LKey', c.font_name, key_fs, (8, 20, 34), bold=True, align=4,
                      box=(c.pal['accent'], round(c.h * 0.010)))]
    times = [c.t(k, n, it.get('on_word'), it.get('at')) for k, it in enumerate(items)]
    for k in range(1, n):  # nunca antes do anterior
        times[k] = max(times[k], times[k - 1] + 0.25)
    dim = '\\alpha&H70&'
    for k, it in enumerate(items):
        y = int(area_top + step * (k + 0.5))
        a, nxt = times[k], (times[k + 1] if k + 1 < n else c.scene_end)
        txt = esc(it.get('text', ''))
        move = f'\\move({x_text + 40},{y},{x_text},{y},0,260)\\fad(220,0)'
        events.append(_ev(a, nxt, 'LItem', f'{{{move}}}{txt}'))
        if nxt < c.scene_end:
            events.append(_ev(nxt, c.scene_end, 'LItem', f'{{\\pos({x_text},{y}){dim}}}{txt}'))
        if has_keys and it.get('key'):
            kx = x_key + int(c.h * 0.010)
            kmove = f'\\move({kx + 40},{y},{kx},{y},0,260)\\fad(220,0)'
            events.append(_ev(a, nxt, 'LKey', f'{{{kmove}}}{esc(it["key"])}'))
            if nxt < c.scene_end:
                events.append(_ev(nxt, c.scene_end, 'LKey', f'{{\\pos({kx},{y}){dim}}}{esc(it["key"])}'))
        elif not has_keys:
            dot = f'{{\\move({x_key + 40},{y},{x_key},{y},0,260)\\fad(220,0)\\c{ass_color(c.pal["accent"])}}}●'
            events.append(_ev(a, c.scene_end, 'LItem', dot))
    return styles, events


def _fmt_number(v, decimals):
    s = f'{v:,.{decimals}f}'
    return s.replace(',', 'X').replace('.', ',').replace('X', '.')


def layout_number(c, bg_path):
    visuals.base_background(c.w, c.h, c.theme, c.channel, c.idx, c.fonts).save(bg_path)
    spec = c.scene.get('number') or {}
    if 'value' not in spec:
        raise StudioError(f'Cena {c.idx}: layout "number" precisa de "number": {{"value": ...}}.')
    styles, events, top = _headline_events(c, size_frac=0.056)
    value, dec = float(spec['value']), int(spec.get('decimals', 0))
    pre, suf = spec.get('prefix', ''), spec.get('suffix', '')
    big = round(c.h * 0.19)
    final_txt = f'{pre}{_fmt_number(value, dec)}{suf}'
    while visuals.text_width(final_txt, c.fonts['bold'], big) > c.w - 2 * c.pad and big > 40:
        big -= 4
    styles += [_style('LBig', c.font_name, big, c.pal['accent'], bold=True, align=1),
               _style('LLabel', c.font_name, round(c.h * 0.048), (255, 255, 255), align=7),
               _style('LSmall', c.font_name, round(c.h * 0.025), (190, 210, 220), align=1)]
    y_big = int(c.h * max(0.56, top + 0.24))
    a = c.t(0, 1, spec.get('on_word'), spec.get('at'))
    dur, steps = 1.2, 24
    for s in range(steps):  # contagem crescente com desaceleração
        t0 = a + dur * s / steps
        p = 1 - (1 - (s + 1) / steps) ** 3
        txt = f'{pre}{_fmt_number(value * p, dec)}{suf}'
        fade = '\\fad(120,0)' if s == 0 else ''
        events.append(_ev(t0, t0 + dur / steps, 'LBig', f'{{\\pos({c.pad},{y_big}){fade}}}{esc(txt)}'))
    events.append(_ev(a + dur, c.scene_end, 'LBig', f'{{\\pos({c.pad},{y_big})}}{esc(final_txt)}'))
    if spec.get('label'):
        lines = visuals.wrap_lines(spec['label'], c.fonts['regular'], round(c.h * 0.048), c.w - 2 * c.pad)[:2]
        events.append(_ev(a + 0.4, c.scene_end, 'LLabel',
                          f'{{\\pos({c.pad},{y_big + int(c.h * 0.025)})\\fad(300,0)}}' + '\\N'.join(esc(x) for x in lines)))
    if spec.get('source'):
        events.append(_ev(a + 0.6, c.scene_end, 'LSmall',
                          f'{{\\pos({c.pad},{int(c.h * 0.835)})\\fad(300,0)}}Fonte: {esc(spec["source"])}'))
    return styles, events


def layout_compare(c, bg_path):
    spec = c.scene.get('compare') or {}
    left, right = spec.get('left') or {}, spec.get('right') or {}
    if not left or not right:
        raise StudioError(f'Cena {c.idx}: layout "compare" precisa de "compare": {{"left": ..., "right": ...}}.')
    styles, events, top = _headline_events(c, size_frac=0.060)
    im = visuals.base_background(c.w, c.h, c.theme, c.channel, c.idx, c.fonts, waves=False)
    draw = ImageDraw.Draw(im, 'RGBA')
    gap = int(c.w * 0.03)
    col_w = (c.w - 2 * c.pad - gap) // 2
    tfs, ifs = round(c.h * 0.044), round(c.h * 0.036)
    inner = int(c.w * 0.02)

    def content_h(side):
        hh = tfs * 1.7
        for it in side.get('items', []):
            text = it['text'] if isinstance(it, dict) else str(it)
            n_l = len(visuals.wrap_lines('• ' + text, c.fonts['regular'], ifs, col_w - 2 * inner)[:2])
            hh += ifs * 1.35 * n_l + ifs * 0.55
        return hh + 2 * inner

    y0 = int(c.h * max(top, 0.32))
    y1 = int(min(c.h * 0.80, y0 + max(content_h(left), content_h(right), c.h * 0.22)))
    boxes = [(c.pad, y0, c.pad + col_w, y1), (c.pad + col_w + gap, y0, c.w - c.pad, y1)]
    draw.rounded_rectangle(boxes[0], radius=c.h // 60, fill=(255, 255, 255, 14),
                           outline=(*c.pal['muted'], 140), width=2)
    draw.rounded_rectangle(boxes[1], radius=c.h // 60, fill=(255, 255, 255, 22),
                           outline=(*c.pal['accent'], 230), width=3)
    im.save(bg_path)
    styles += [_style('LColA', c.font_name, tfs, c.pal['muted'], bold=True),
               _style('LColB', c.font_name, tfs, c.pal['accent'], bold=True),
               _style('LCItem', c.font_name, ifs, (255, 255, 255))]
    seq = [(0, left, 'LColA'), (1, right, 'LColB')]
    all_items = [(col, it) for col, side, _ in seq for it in side.get('items', [])]
    total = len(all_items) + 2
    n = 0
    for col, side, st in seq:
        x = boxes[col][0] + inner
        y = boxes[col][1] + inner
        a = c.t(n, total, side.get('on_word'), side.get('at'))
        n += 1
        events.append(_ev(a, c.scene_end, st, f'{{\\pos({x},{y})\\fad(250,0)}}{esc(side.get("title", ""))}'))
        y += int(tfs * 1.7)
        for it in side.get('items', []):
            it = it if isinstance(it, dict) else {'text': str(it)}
            a2 = max(a + 0.2, c.t(n, total, it.get('on_word'), it.get('at')))
            n += 1
            lines = visuals.wrap_lines('• ' + it['text'], c.fonts['regular'], ifs, col_w - 2 * inner)[:2]
            events.append(_ev(a2, c.scene_end, 'LCItem',
                              f'{{\\pos({x},{y})\\fad(250,0)}}' + '\\N'.join(esc(z) for z in lines)))
            y += int(ifs * 1.35 * len(lines) + ifs * 0.55)
            a = a2
    return styles, events


def layout_quote(c, bg_path):
    spec = c.scene.get('quote') or {}
    if not spec.get('text'):
        raise StudioError(f'Cena {c.idx}: layout "quote" precisa de "quote": {{"text": ...}}.')
    im = visuals.base_background(c.w, c.h, c.theme, c.channel, c.idx, c.fonts, waves=False)
    draw = ImageDraw.Draw(im, 'RGBA')
    qf = ImageFont.truetype(str(c.fonts['bold']), int(c.h * 0.36))
    draw.text((c.pad - int(c.h * 0.02), int(c.h * 0.13)), '“', font=qf, fill=(*c.pal['accent'], 120))
    im.save(bg_path)
    size = round(c.h * 0.060)
    max_w = c.w - 2 * c.pad - int(c.w * 0.06)
    lines = visuals.wrap_lines(spec['text'], c.fonts['bold'], size, max_w)
    while len(lines) > 4 and size > 28:
        size -= 2
        lines = visuals.wrap_lines(spec['text'], c.fonts['bold'], size, max_w)
    styles = [_style('LQuote', c.font_name, size, (255, 255, 255), bold=True),
              _style('LAuthor', c.font_name, round(c.h * 0.036), c.pal['accent'])]
    x, y = c.pad + int(c.w * 0.06), int(c.h * 0.36)
    a = c.t(0, 1, spec.get('on_word'), spec.get('at'))
    events = [_ev(a, c.scene_end, 'LQuote', f'{{\\pos({x},{y})\\fad(450,0)}}' + '\\N'.join(esc(z) for z in lines))]
    if spec.get('author'):
        ya = y + int(size * 1.25 * len(lines) + c.h * 0.04)
        events.append(_ev(a + 0.6, c.scene_end, 'LAuthor', f'{{\\pos({x},{ya})\\fad(300,0)}}— {esc(spec["author"])}'))
    return styles, events


def layout_chart(c, bg_path):
    spec = c.scene.get('chart') or {}
    styles, events, top = _headline_events(c, size_frac=0.058)
    bg = visuals.base_background(c.w, c.h, c.theme, c.channel, c.idx, c.fonts, waves=False)
    charts.render_chart(spec, bg, bg_path, c.w, c.h, c.pal['accent'], c.pal['muted'], c.fonts['regular'],
                        top=max(0.27, top + 0.02), bottom=0.80)
    if spec.get('source'):
        styles.append(_style('LSmall', c.font_name, round(c.h * 0.025), (190, 210, 220), align=1))
        events.append(_ev(0.3, c.scene_end, 'LSmall', f'{{\\pos({c.pad},{int(c.h * 0.845)})\\fad(300,0)}}'
                                                      f'Fonte: {esc(spec["source"])}'))
    return styles, events


def image_overlay(c):
    """Título opcional sobre imagens (\"overlay_title\": true)."""
    if not c.scene.get('overlay_title'):
        return [], []
    styles, events, _ = _headline_events(c, y_frac=0.19, size_frac=0.064)
    styles[0] = styles[0].replace(',0,0,7,0,0,0,1', f',{max(2, c.h // 360)},{max(1, c.h // 540)},7,0,0,0,1')
    return styles, events


BUILDERS = {'list': layout_list, 'number': layout_number, 'compare': layout_compare,
            'quote': layout_quote, 'chart': layout_chart}
