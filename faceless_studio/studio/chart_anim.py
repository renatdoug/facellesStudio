"""Gráficos animados desenhados em ASS (vetor, nítido em qualquer resolução).

- barras (vertical e horizontal) crescem do eixo, com o valor subindo junto (contagem);
- linhas se desenham da esquerda para a direita e cada ponto "salta" quando a linha chega nele.

Tudo é feito com desenhos ASS (\\p1) e a animação \\clip, sem renderizar quadro a quadro. Cada barra
pode entrar na palavra da narração indicada em "on_words" (uma por rótulo); sem isso, entram em
sequência. A versão estática (matplotlib, charts.py) continua disponível com "animate": false.
"""
import math

from . import visuals
from .ass_helpers import ev, style
from .subtitles import ass_color, esc, find_word_time
from .util import StudioError

KINDS = ('bar', 'barh', 'line')
GROW = 0.85          # s que uma barra leva para crescer
LINE_GROW = 1.5      # s que a linha leva para ser desenhada
STAGGER = 0.22       # s entre uma barra e a próxima, quando não há "on_words"
STEPS = 14           # quantos valores intermediários a contagem mostra
LINE_COLORS = [None, None, (255, 191, 140), (191, 166, 255)]  # None = acento / cinza do tema


def supports(spec):
    """O gráfico animado cobre barras simples e linhas (uma ou várias séries)."""
    if spec.get('animate', True) is False:
        return False
    kind = spec.get('type', 'bar')
    series = spec.get('series')
    return kind in KINDS and (kind == 'line' or not series or len(series) == 1)


def _fmt(spec):
    unit, dec = spec.get('unit', ''), int(spec.get('decimals', 0))

    def fmt(v):
        txt = f'{v:,.{dec}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
        return f'{txt}{unit}'
    return fmt


def _rect(x1, y1, x2, y2):
    return f'm {x1:.1f} {y1:.1f} l {x2:.1f} {y1:.1f} {x2:.1f} {y2:.1f} {x1:.1f} {y2:.1f}'


def _shape(color, alpha=0):
    a = f'\\1a&H{alpha:02X}&' if alpha else ''
    return f'\\an7\\pos(0,0)\\bord0\\shad0\\1c{ass_color(color)}{a}'


def _fit(labels, font_path, size, max_w, floor):
    """Menor fonte (até `floor`) com que o maior rótulo cabe em `max_w`."""
    while size > floor and max(visuals.text_width(x, font_path, size) for x in labels) > max_w:
        size -= 2
    return size


def _starts(c, spec, n, t0):
    """Momento de entrada de cada barra: na palavra de "on_words" quando ela existe na narração;
    senão, logo depois da barra anterior (nunca antes dela)."""
    words = spec.get('on_words') if isinstance(spec.get('on_words'), list) else []
    out = []
    for i in range(n):
        target = str(words[i]) if i < len(words) and words[i] else ''
        found = find_word_time(c.words, target, None) if target else None
        if found is not None:
            out.append(max(c.speech_start, found))
        else:
            out.append(t0 if not out else out[-1] + STAGGER)
    return out


def _nice_ticks(lo, hi, count=4):
    """Marcas "redondas" (1, 2, 2.5, 5 x 10^k) entre lo e hi."""
    raw = (hi - lo) / count
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m for m in (1, 2, 2.5, 5, 10) if m * mag >= raw) * mag
    first = math.ceil(lo / step - 1e-9) * step
    out, v = [], first
    while v <= hi + 1e-9:
        out.append(v)
        v += step
    return out


def _prefers_horizontal(c, spec, labels, slot):
    orient = spec.get('orient', 'auto')
    if orient in ('vertical', 'horizontal'):
        return orient == 'horizontal'
    size = round(c.h * 0.030)
    return max(visuals.text_width(x, c.fonts['regular'], size) for x in labels) > slot * 0.95


def build(c, spec, top, bottom):
    """Devolve (estilos ASS, eventos ASS) do gráfico animado. O fundo é só o da cena."""
    labels = [str(x) for x in spec.get('labels', [])]
    series = spec.get('series') or [{'name': '', 'values': spec.get('values', [])}]
    if not labels or any(len(s.get('values', [])) != len(labels) for s in series):
        raise StudioError('Gráfico: "labels" e "values" precisam ter o mesmo tamanho.')
    kind = spec.get('type', 'bar')
    x0, x1 = c.pad, c.w - c.pad
    y0, y1 = int(c.h * top), int(c.h * bottom)
    if kind == 'bar' and _prefers_horizontal(c, spec, labels, (x1 - x0) / len(labels)):
        kind = 'barh'
    t0 = c.t(0, 1, spec.get('on_word'), spec.get('at'))
    builder = {'bar': _bars_v, 'barh': _bars_h, 'line': _lines}[kind]
    return builder(c, spec, labels, series, (x0, y0, x1, y1), t0)


def _styles(c, lab, val):
    f, acc = c.font_name, c.pal['accent']
    white = (255, 255, 255)
    return [style('CBar', f, 10, acc),
            style('CLab', f, lab, white, align=8),                 # topo centro (sob a barra)
            style('CLabR', f, lab, white, align=6),                # meio direita (ao lado da barra)
            style('CTick', f, round(lab * 0.85), (190, 210, 220), align=6),
            style('CVal', f, val, white, bold=True, align=2),      # base centro (acima da barra)
            style('CValL', f, val, white, bold=True, align=4),     # meio esquerda (ponta da barra)
            style('CLeg', f, round(lab * 0.9), white, align=4)]


def _baseline(c, x1, x2, y, t0):
    thick = max(2, round(c.h / 520))
    return ev(t0, c.scene_end, 'CBar',
              f'{{{_shape((255, 255, 255), 0x99)}\\fad(250,0)\\p1}}{_rect(x1, y, x2, y + thick)}{{\\p0}}')


def _bar_colors(c, spec, i):
    hl = spec.get('highlight')
    if hl is None or i == hl:
        return c.pal['accent'], 0
    return c.pal['muted'], 0x73  # cinza com ~55% de opacidade, como no gráfico estático


def _bars_v(c, spec, labels, series, area, t0):
    x0, y0, x1, y1 = area
    vals = [float(v) for v in series[0]['values']]
    n, fmt = len(vals), _fmt(spec)
    slot = (x1 - x0) / n
    lab = _fit(labels, c.fonts['regular'], round(c.h * 0.030), slot * 0.92, round(c.h * 0.018))
    val = round(lab * 1.2)
    base = y1 - int(lab * 1.7)
    top_y = y0 + int(val * 1.8)
    vmax = max(max(vals), 1e-9)
    bar_w = min(slot * 0.62, c.h * 0.16)
    gap = max(6, round(c.h * 0.010))
    ms = int(GROW * 1000)
    events = [_baseline(c, x0, x1, base, t0)]
    starts = _starts(c, spec, n, t0)
    for i, (name, v) in enumerate(zip(labels, vals)):
        a = starts[i]
        xc = x0 + slot * (i + 0.5)
        bx1, bx2 = int(xc - bar_w / 2), int(xc + bar_w / 2)
        bh = (base - top_y) * max(v, 0) / vmax
        yt = int(base - bh)
        color, alpha = _bar_colors(c, spec, i)
        events.append(ev(a, c.scene_end, 'CLab', f'{{\\pos({xc:.0f},{base + gap})\\fad(220,0)}}{esc(name)}'))
        events.append(ev(a, c.scene_end, 'CBar',
                         f'{{{_shape(color, alpha)}\\clip({bx1},{base},{bx2},{base})'
                         f'\\t(0,{ms},0.5,\\clip({bx1},{yt},{bx2},{base}))\\p1}}{_rect(bx1, yt, bx2, base)}{{\\p0}}'))
        for s in range(1, STEPS + 1):  # o valor sobe junto com o topo da barra
            p = (s / STEPS) ** 0.5     # mesma curva (accel 0.5) do \t da barra
            ts, te = a + GROW * (s - 1) / STEPS, (a + GROW * s / STEPS if s < STEPS else c.scene_end)
            events.append(ev(ts, te, 'CVal', f'{{\\pos({xc:.0f},{base - bh * p - gap:.0f})}}{esc(fmt(v * p))}',
                             min_dur=0.03))
    return _styles(c, lab, val), events


def _bars_h(c, spec, labels, series, area, t0):
    x0, y0, x1, y1 = area
    vals = [float(v) for v in series[0]['values']]
    n, fmt = len(vals), _fmt(spec)
    row = (y1 - y0) / n
    lab = _fit(labels, c.fonts['regular'], round(c.h * 0.030), (x1 - x0) * 0.40, round(c.h * 0.018))
    val = round(lab * 1.2)
    gap = max(8, round(c.h * 0.012))
    label_w = max(visuals.text_width(x, c.fonts['regular'], lab) for x in labels)
    bx0 = int(x0 + label_w + gap * 1.5)
    vmax = max(max(vals), 1e-9)
    val_w = max(visuals.text_width(fmt(v), c.fonts['bold'], val) for v in vals) + gap
    span = max(10, x1 - val_w - bx0)
    bar_h = min(row * 0.58, c.h * 0.075)
    ms = int(GROW * 1000)
    thick = max(2, round(c.h / 520))
    events = [ev(t0, c.scene_end, 'CBar', f'{{{_shape((255, 255, 255), 0x99)}\\fad(250,0)\\p1}}'
                                          f'{_rect(bx0 - thick, y0, bx0, y1)}{{\\p0}}')]
    starts = _starts(c, spec, n, t0)
    for i, (name, v) in enumerate(zip(labels, vals)):
        a = starts[i]
        yc = y0 + row * (i + 0.5)
        by1, by2 = int(yc - bar_h / 2), int(yc + bar_h / 2)
        ln = span * max(v, 0) / vmax
        xe = int(bx0 + ln)
        color, alpha = _bar_colors(c, spec, i)
        events.append(ev(a, c.scene_end, 'CLabR', f'{{\\pos({bx0 - gap:.0f},{yc:.0f})\\fad(220,0)}}{esc(name)}'))
        events.append(ev(a, c.scene_end, 'CBar',
                         f'{{{_shape(color, alpha)}\\clip({bx0},{by1},{bx0},{by2})'
                         f'\\t(0,{ms},0.5,\\clip({bx0},{by1},{xe},{by2}))\\p1}}{_rect(bx0, by1, xe, by2)}{{\\p0}}'))
        for s in range(1, STEPS + 1):
            p = (s / STEPS) ** 0.5
            ts, te = a + GROW * (s - 1) / STEPS, (a + GROW * s / STEPS if s < STEPS else c.scene_end)
            events.append(ev(ts, te, 'CValL', f'{{\\pos({bx0 + ln * p + gap:.0f},{yc:.0f})}}{esc(fmt(v * p))}',
                             min_dur=0.03))
    return _styles(c, lab, val), events


def _circle(r):
    k = 0.5523 * r  # aproximação de círculo por 4 curvas de Bézier
    d = 2 * r
    return (f'm 0 {r:.1f} b 0 {r - k:.1f} {r - k:.1f} 0 {r:.1f} 0 b {r + k:.1f} 0 {d:.1f} {r - k:.1f} {d:.1f} {r:.1f} '
            f'b {d:.1f} {r + k:.1f} {r + k:.1f} {d:.1f} {r:.1f} {d:.1f} b {r - k:.1f} {d:.1f} 0 {r + k:.1f} 0 {r:.1f}')


def _lines(c, spec, labels, series, area, t0):
    x0, y0, x1, y1 = area
    n, fmt = len(labels), _fmt(spec)
    flat = [float(v) for s in series for v in s['values']]
    fmin, fmax = min(flat), max(flat)
    rng = (fmax - fmin) or max(abs(fmax), 1.0)
    lo, hi = fmin - rng * 0.25, fmax + rng * 0.25  # escala automática, sem forçar o zero
    if spec.get('zero'):
        lo = min(0.0, fmin)
    slot = (x1 - x0) / max(n, 1)
    lab = _fit(labels, c.fonts['regular'], round(c.h * 0.030), slot * 0.95, round(c.h * 0.018))
    val = round(lab * 1.1)
    gap = max(6, round(c.h * 0.010))
    base = y1 - int(lab * 1.7)
    top_y = y0 + int(val * 1.4)
    ticks = _nice_ticks(lo, hi)
    tick_w = max(visuals.text_width(fmt(v), c.fonts['regular'], round(lab * 0.85)) for v in ticks) + gap * 1.5
    point_w = max(visuals.text_width(fmt(float(v)), c.fonts['bold'], val) for s in series for v in s['values'])
    px0 = x0 + tick_w + point_w / 2 + gap
    px1 = max(px0 + 40, x1 - point_w / 2)
    show_all = n > 1 and len(series) == 1 and point_w * 1.35 < (px1 - px0) / (n - 1)
    xs = [(px0 + px1) / 2] if n == 1 else [px0 + (px1 - px0) * i / (n - 1) for i in range(n)]

    def ypos(v):
        return base - (v - lo) / (hi - lo) * (base - top_y)

    events = [_baseline(c, x0, x1, base, t0)]
    for v in ticks:  # grade horizontal discreta + valores do eixo
        y = ypos(v)
        events.append(ev(t0, c.scene_end, 'CBar', f'{{{_shape((255, 255, 255), 0xE6)}\\fad(250,0)\\p1}}'
                                                  f'{_rect(x0, y, x1, y + max(1, round(c.h / 900)))}{{\\p0}}'))
        events.append(ev(t0, c.scene_end, 'CTick', f'{{\\pos({x0 + tick_w - gap:.0f},{y:.0f})\\fad(250,0)}}{esc(fmt(v))}'))
    skip = max(1, math.ceil(max(visuals.text_width(x, c.fonts['regular'], lab) for x in labels) / (slot * 0.95)))
    for i, name in enumerate(labels):
        if i % skip == 0 or i == n - 1:
            events.append(ev(t0, c.scene_end, 'CLab', f'{{\\pos({xs[i]:.0f},{base + gap})\\fad(250,0)}}{esc(name)}'))
    styles = _styles(c, lab, val)
    lw = max(3, round(c.h / 270))
    r = lw * 1.25
    ms = int(LINE_GROW * 1000)
    multi = len(series) > 1
    for si, s in enumerate(series):
        color = LINE_COLORS[si % len(LINE_COLORS)] or (c.pal['accent'] if si % 2 == 0 else c.pal['muted'])
        a = t0 + si * 0.35
        pts = [(xs[i], ypos(float(v))) for i, v in enumerate(s['values'])]
        fwd = ' '.join(f'{x:.1f} {y:.1f}' for x, y in pts)
        back = ' '.join(f'{x:.1f} {y:.1f}' for x, y in reversed(pts[1:-1]))
        # ida e volta pelos mesmos pontos: o contorno (\bord) vira a linha grossa de pontas arredondadas
        path = f'm {pts[0][0]:.1f} {pts[0][1]:.1f} l {fwd} {back}'
        left, right = px0 - lw * 2, px1 + lw * 2
        events.append(ev(a, c.scene_end, 'CBar',
                         f'{{\\an7\\pos(0,0)\\shad0\\bord{lw}\\1a&HFF&\\3a&H00&\\3c{ass_color(color)}'
                         f'\\clip({left:.0f},0,{left:.0f},{c.h})\\t(0,{ms},1,\\clip({left:.0f},0,{right:.0f},{c.h}))'
                         f'\\p1}}{path}{{\\p0}}'))
        for i, (px, py) in enumerate(pts):
            hit = a + LINE_GROW * (px - px0) / max(1.0, px1 - px0)  # quando a linha chega neste ponto
            pop = '\\fscx10\\fscy10\\t(0,160,\\fscx100\\fscy100)'
            events.append(ev(hit, c.scene_end, 'CBar',
                             f'{{\\an5\\pos({px:.1f},{py:.1f})\\bord0\\shad0\\1c{ass_color(color)}{pop}\\p1}}'
                             f'{_circle(r)}{{\\p0}}'))
            if i == n - 1 or show_all:
                events.append(ev(hit, c.scene_end, 'CVal', f'{{\\pos({px:.0f},{py - r - gap:.0f})\\fad(200,0)}}'
                                                           f'{esc(fmt(float(s["values"][i])))}'))
        if multi and s.get('name'):
            ly = y0 + (val * 1.2) * si
            events.append(ev(a, c.scene_end, 'CLeg', f'{{\\pos({x0 + tick_w:.0f},{ly:.0f})\\fad(250,0)\\1c{ass_color(color)}}}'
                                                     f'■ {{\\1c&HFFFFFF&}}{esc(s["name"])}'))
    return styles, events
