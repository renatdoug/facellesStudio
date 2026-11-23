"""Ilustrações animadas das cenas de cartum ("demo"): a "tela" na parede mostra o que a fala descreve
(um ninja correndo sobre a água, uma fórmula escrita aos poucos). Tudo desenhado por código, em preto e branco,
sem IA e sem custo. `render()` devolve o painel (RGBA) de um instante; o `Stage` o posiciona e o anima (entrada com "pop").
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFont

INK = (22, 22, 22)
PAPER = (252, 252, 252)
VISUALS = ('ninja_water', 'formula', 'hero_hit')
FRAMES = ('screen', 'bubble')  # tela retangular na parede ou balão de pensamento (com bolinhas até quem fala)
MAX_FORMULA = 40
DESIGN_H = 360  # o desenho é pensado numa altura de 360 unidades; `S` = altura real / 360


def demo_spec(raw) -> dict | None:
    """Aceita "ninja_water" ou {"type": "formula", "text": "..."}; devolve sempre um dicionário (ou None)."""
    if raw in (None, '', False):
        return None
    return {'type': raw} if isinstance(raw, str) else dict(raw)


def validate_demo(raw, demo_at, n: int) -> None:
    spec = demo_spec(raw)
    if not isinstance(spec, dict) or spec.get('type') not in VISUALS:
        raise ValueError(f'Cena {n}: "demo" deve ser ' + ', '.join(VISUALS) + ' (ou um objeto {"type": ..., "text": ...}).')
    if spec['type'] == 'formula':
        text = spec.get('text')
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_FORMULA:
            raise ValueError(f'Cena {n}: "demo" do tipo formula precisa de "text" (até {MAX_FORMULA} caracteres).')
    if spec.get('frame', 'screen') not in FRAMES:
        raise ValueError(f'Cena {n}: "demo" tem "frame" inválido: use ' + ' ou '.join(FRAMES) + '.')
    if demo_at is not None and (isinstance(demo_at, bool) or not isinstance(demo_at, (int, float)) or demo_at < 0):
        raise ValueError(f'Cena {n}: "demo_at" deve ser um número de segundos (0 ou mais).')


class _Pen:
    """Desenha em unidades de projeto (altura 360) na escala real do painel."""

    def __init__(self, img: Image.Image, S: float):
        self.img, self.d, self.S = img, ImageDraw.Draw(img), S
        self.z, self.zo = 1.0, (0.0, 0.0)  # zoom (e o ponto fixo) aplicado a tudo que se desenha depois

    def tx(self, x, y):
        """Unidades de projeto -> pixels, com o zoom."""
        return ((self.zo[0] + (x - self.zo[0]) * self.z) * self.S, (self.zo[1] + (y - self.zo[1]) * self.z) * self.S)

    def line(self, pts, w, fill=INK):
        P = [self.tx(x, y) for x, y in pts]
        wpx = max(1, round(w * self.z * self.S))
        self.d.line(P, fill=fill, width=wpx, joint='curve')
        r = wpx / 2
        for x, y in (P[0], P[-1]):
            self.d.ellipse((x - r, y - r, x + r, y + r), fill=fill)

    def circle(self, cx, cy, r, fill=None, outline=None, w=3):
        (x0, y0), (x1, y1) = self.tx(cx - r, cy - r), self.tx(cx + r, cy + r)
        self.d.ellipse((x0, y0, x1, y1), fill=fill, outline=outline,
                       width=max(1, round(w * self.z * self.S)) if outline else 0)

    def ellipse(self, cx, cy, rx, ry, fill=None, outline=None, w=3):
        (x0, y0), (x1, y1) = self.tx(cx - rx, cy - ry), self.tx(cx + rx, cy + ry)
        self.d.ellipse((x0, y0, x1, y1), fill=fill, outline=outline, width=max(1, round(w * self.z * self.S)) if outline else 0)

    def poly(self, pts, fill=None, outline=None, w=3):
        P = [self.tx(x, y) for x, y in pts]
        self.d.polygon(P, fill=fill)
        if outline:
            self.d.line(P + [P[0]], fill=outline, width=max(1, round(w * self.z * self.S)), joint='curve')

    def ring(self, x0, y0, x1, y1, outline, w=2):
        (a, b), (c, d) = self.tx(x0, y0), self.tx(x1, y1)
        self.d.ellipse((a, b, c, d), outline=outline, width=max(1, round(w * self.z * self.S)))

    def rect(self, x0, y0, x1, y1, fill=None, outline=None, w=3, r=0):
        (a, b), (c, d) = self.tx(x0, y0), self.tx(x1, y1)
        wpx = max(1, round(w * self.z * self.S))
        if r:
            self.d.rounded_rectangle((a, b, c, d), radius=r * self.z * self.S, fill=fill, outline=outline, width=wpx)
        else:
            self.d.rectangle((a, b, c, d), fill=fill, outline=outline, width=wpx)


def _hash01(*parts) -> float:
    import zlib
    return (zlib.crc32('|'.join(map(str, parts)).encode()) % 1000) / 1000.0


def _limb(hip_or_shoulder, a1, l1, a2, l2):
    """Membro de duas partes: ângulos medidos a partir da vertical para baixo, positivo = para a frente (direita)."""
    x0, y0 = hip_or_shoulder
    x1, y1 = x0 + l1 * math.sin(math.radians(a1)), y0 + l1 * math.cos(math.radians(a1))
    x2, y2 = x1 + l2 * math.sin(math.radians(a2)), y1 + l2 * math.cos(math.radians(a2))
    return (x0, y0), (x1, y1), (x2, y2)


def _ninja_water(pen: _Pen, W: float, H: float, u: float) -> None:
    water = H * 0.74
    pen.rect(0, 0, W, water, fill=(246, 246, 246))
    pen.rect(0, water, W, H, fill=(206, 206, 206))
    pen.line([(0, water), (W, water)], 3, (110, 110, 110))
    for row in range(4):  # ondas que correm para trás: o ninja corre "parado" e a água passa
        y = water + 12 + row * 17
        off = u * (260 + 90 * row) % 120
        pts = [(x, y + 3.5 * math.sin((x + off) / 14 + row)) for x in range(-130, int(W) + 130, 10)]
        pen.line([(x - off, yy) for x, yy in pts], 2.4, (150, 150, 150))
    x0 = W * 0.42
    pen.z, pen.zo = 1.22, (x0, water)  # o ninja (e o que o acompanha) é desenhado maior, com os pés na linha da água
    phase = 2 * math.pi * u * 3.4  # passadas rápidas
    bob = 7 * abs(math.sin(phase))
    hip = (x0, water - 80 - bob)
    lean = 24  # tronco inclinado para a frente
    sh = (hip[0] + 56 * math.sin(math.radians(lean)), hip[1] - 56 * math.cos(math.radians(lean)))
    feet = []
    for k, sgn in enumerate((1, -1)):  # pernas em oposição
        a = 52 * math.sin(phase + k * math.pi)
        flex = 18 + 62 * max(0.0, -math.sin(phase + k * math.pi + 0.6))
        pts = _limb(hip, a, 40, a - flex, 42)
        pen.line(pts, 11)
        feet.append(pts[2])
    # rastro de respingos e anéis na água, atrás dos pés
    for i in range(7):
        fx = x0 - 18 - i * 17 - (u * 140 % 17)
        fy = water + 2 - 14 * abs(math.sin(u * 9 + i * 1.3)) * (1 - i / 8)
        pen.circle(fx, fy, 3.2 - i * 0.25, fill=(120, 120, 120))
    for i in range(3):
        grow = (u * 1.6 + i / 3) % 1.0
        pen.ring(x0 - 40 - 150 * grow - 30 * grow, water + 6, x0 - 40 - 150 * grow + 30 * grow, water + 9 + 14 * grow,
                 (120, 120, 120), 2.2)
    # braços balançando em oposição ao das pernas
    for k in range(2):
        a = -55 * math.sin(phase + k * math.pi)
        pen.line(_limb((sh[0], sh[1] + 4), a, 26, a - 70, 26), 9)
    # corpo, capuz com faixa branca dos olhos, rabos esvoaçantes da faixa
    pen.line([hip, sh], 18)
    hc = (sh[0] + 9, sh[1] - 21)
    pen.circle(hc[0], hc[1], 22, fill=INK)
    pen.rect(hc[0] - 9, hc[1] - 8, hc[0] + 21, hc[1] + 6, fill=PAPER, r=4)
    pen.circle(hc[0] + 6, hc[1] - 1, 2.6, fill=INK)
    pen.circle(hc[0] + 15, hc[1] - 1, 2.6, fill=INK)
    for j, off in enumerate((-6, 5)):
        tail = [(hc[0] - 20, hc[1] + off)]
        for s in range(1, 8):
            tail.append((hc[0] - 20 - s * 9, hc[1] + off + 7 * math.sin(phase * 1.5 - s * 0.9 + j) * (s / 5)))
        pen.line(tail, 5)
    for i in range(6):  # linhas de velocidade
        ly = water - 150 + i * 24 + 4 * _hash01('v', i)
        lx = (x0 - 70 - ((u * 620 + i * 97) % 240))
        pen.line([(lx, ly), (lx - 38 - 40 * _hash01('l', i), ly)], 3, (96, 96, 96))


def _star(pen, cx, cy, r):
    pts = []
    for i in range(8):
        a = math.radians(-90 + i * 45)
        rr = r if i % 2 == 0 else r * 0.42
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    pen.poly(pts, fill=PAPER, outline=INK, w=2.5)


def _hero_hit(pen: _Pen, W: float, H: float, u: float, font_path) -> None:
    """Um herói fictício de anime leva uma pancada cartunesca (martelo de brinquedo), fica tonto com estrelas e
    levanta rindo. Sem violência gráfica. O ciclo se repete a cada `PERIOD` segundos."""
    PERIOD, T_HIT = 3.4, 0.85
    v = u % PERIOD
    dt = v - T_HIT
    ground = H * 0.82
    x0 = W * 0.42
    pen.rect(0, 0, W, H, fill=(246, 246, 246))
    pen.rect(0, ground, W, H, fill=(214, 214, 214))
    pen.line([(0, ground), (W, ground)], 3, (120, 120, 120))
    pen.z, pen.zo = 1.18, (x0, ground)  # herói e martelo maiores, com os pés no chão
    lean = 14 * math.exp(-dt * 2.6) * math.sin(dt * 20) if dt >= 0 else 0.0
    squash = max(0.0, 1.0 - dt / 0.28) if 0 <= dt < 0.28 else 0.0
    hip = (x0 + lean * 0.3, ground - 66)
    neck = (x0 + lean * 0.7, ground - 66 - 74)
    r = 28
    hc = (neck[0] + lean * 0.4, neck[1] - 24 + 11 * squash)
    # capa (cinza) esvoaçando atrás
    flutter = 6 * math.sin(u * 7)
    pen.poly([(neck[0] - 4, neck[1] + 4), (neck[0] - 62, neck[1] + 80 + flutter), (neck[0] - 30, neck[1] + 92), (neck[0] + 6, neck[1] + 30)],
             fill=(150, 150, 150), outline=INK, w=3)
    # pernas, tronco e braços
    pen.line([hip, (x0 - 20, ground)], 12)
    pen.line([hip, (x0 + 20, ground)], 12)
    pen.line([hip, neck], 16)
    happy = v >= 2.3
    pen.line([(neck[0] - 4, neck[1] + 8), (x0 - 32 + lean, neck[1] + 62)], 10)
    if happy:  # levanta rindo: braço para o alto, punho fechado
        arm = [(neck[0] + 4, neck[1] + 8), (neck[0] + 38, neck[1] - 10), (neck[0] + 46, neck[1] - 48 + 4 * math.sin(u * 9))]
        pen.line(arm, 10)
        pen.circle(arm[-1][0], arm[-1][1], 7, fill=PAPER, outline=INK, w=3)
    else:
        pen.line([(neck[0] + 4, neck[1] + 8), (x0 + 32 + lean, neck[1] + 62)], 10)
    # cabeça: achatada no impacto; cabelo espetado de herói
    pen.ellipse(hc[0], hc[1], r * (1 + 0.22 * squash), r * (1 - 0.26 * squash), fill=PAPER, outline=INK, w=5)
    top = hc[1] - r * (1 - 0.26 * squash)
    pen.poly([(hc[0] - 26, top + 10), (hc[0] - 30, top - 18), (hc[0] - 14, top - 2), (hc[0] - 8, top - 30), (hc[0] + 4, top - 4),
              (hc[0] + 16, top - 28), (hc[0] + 22, top - 2), (hc[0] + 34, top - 18), (hc[0] + 26, top + 10)], fill=INK, outline=INK, w=2)
    pen.line([(hc[0] - r * 0.95, hc[1] - 6), (hc[0] + r * 0.95, hc[1] - 6)], 5, (90, 90, 90))  # faixa na testa
    for ex in (-1, 1):
        cx, cy = hc[0] + ex * 11, hc[1] + 4
        if happy:
            pen.line([(cx - 6, cy + 3), (cx, cy - 4), (cx + 6, cy + 3)], 3)
        elif dt >= 0:  # tonto: olhos em espiral
            pen.circle(cx, cy, 7, outline=INK, w=2.5)
            pen.circle(cx, cy, 2.2, fill=INK)
        else:
            pen.circle(cx, cy, 3.6, fill=INK)
    if happy:
        pen.line([(hc[0] - 10, hc[1] + 14), (hc[0] - 4, hc[1] + 20), (hc[0] + 4, hc[1] + 20), (hc[0] + 10, hc[1] + 14)], 3)
    elif dt >= 0:
        pen.ellipse(hc[0], hc[1] + 17, 6, 4, fill=INK)
    else:
        pen.line([(hc[0] - 7, hc[1] + 16), (hc[0] + 7, hc[1] + 16)], 3)
    # martelo de brinquedo: levanta, balança, bate e volta (pivô calculado para a cabeça do herói ficar no ponto de impacto)
    L, th_hit = 150, 125.0
    pivot = (x0 + 144, ground - 192 - 101)  # fixo: a cabeça do martelo cai sobre o topo da cabeça do herói em repouso (o martelo entra por cima do quadro)
    if v < 0.7:
        th = 25 - 20 * (v / 0.7) ** 2
    elif v < 0.85:
        th = 5 + (th_hit - 5) * ((v - 0.7) / 0.15) ** 2
    elif v < 1.15:
        th = th_hit
    elif v < 1.9:
        k = (v - 1.15) / 0.75
        th = th_hit - (th_hit - 25) * (k * k * (3 - 2 * k))
    else:
        th = 25
    d = (-math.sin(math.radians(th)), -math.cos(math.radians(th)))
    end = (pivot[0] + L * d[0], pivot[1] + L * d[1])
    nrm = (-d[1], d[0])
    pen.line([pivot, end], 9, (80, 80, 80))
    hw, hh = 40, 24
    c1 = (end[0] + nrm[0] * hh + d[0] * 6, end[1] + nrm[1] * hh + d[1] * 6)
    c2 = (end[0] - nrm[0] * hh + d[0] * 6, end[1] - nrm[1] * hh + d[1] * 6)
    c3 = (c2[0] + d[0] * hw, c2[1] + d[1] * hw)
    c4 = (c1[0] + d[0] * hw, c1[1] + d[1] * hw)
    pen.poly([c1, c2, c3, c4], fill=(205, 205, 205), outline=INK, w=3.5)
    # estrelas girando e "POW!" no impacto
    if 0 <= dt < 1.45:
        for k in range(3):
            a = 7 * dt + k * 2 * math.pi / 3
            _star(pen, hc[0] + 46 * math.cos(a), hc[1] - r - 10 + 11 * math.sin(a), 9)
    if 0 <= dt < 0.5:
        bx, by = hc[0] - 84, hc[1] - 52
        sc = 0.7 + 0.5 * min(1.0, dt / 0.12)
        burst = []
        for i in range(16):
            a = math.radians(i * 22.5)
            rr = (52 if i % 2 == 0 else 30) * sc
            burst.append((bx + rr * math.cos(a), by + rr * 0.8 * math.sin(a)))
        pen.poly(burst, fill=PAPER, outline=INK, w=3)
        from .visuals import find_font
        font = ImageFont.truetype(str(font_path or find_font(True)), max(8, round(24 * sc * pen.S)))
        pen.d.text(pen.tx(bx, by), 'POW!', font=font, fill=INK, anchor='mm')


def _formula(pen: _Pen, W: float, H: float, u: float, font_path) -> None:
    pen.rect(0, 0, W, H, fill=(250, 250, 250))
    for gx in range(0, int(W), 30):  # papel quadriculado
        pen.line([(gx, 0), (gx, H)], 1, (226, 226, 226))
    for gy in range(0, int(H), 30):
        pen.line([(0, gy), (W, gy)], 1, (226, 226, 226))


def _text_formula(img: Image.Image, S: float, W: float, H: float, u: float, text: str, font_path) -> None:
    from .visuals import find_font
    path = font_path or find_font(True)
    lines = [text]
    if len(text) > 16 and ' ' in text:  # texto longo: duas linhas (letra maior e mais legível)
        words, best = text.split(' '), None
        for i in range(1, len(words)):
            a, b = ' '.join(words[:i]), ' '.join(words[i:])
            if best is None or abs(len(a) - len(b)) < best[0]:
                best = (abs(len(a) - len(b)), [a, b])
        lines = best[1]
    size = int(H * S * (0.30 if len(lines) == 1 else 0.24))
    while size > 10:
        font = ImageFont.truetype(str(path), size)
        if max(font.getlength(ln) for ln in lines) <= W * S * 0.86:
            break
        size -= 2
    d = ImageDraw.Draw(img)
    total = len(text)
    typed = int(u * 16)  # escreve aos poucos
    block_h = size * 1.25 * len(lines)
    y0 = (H * S - block_h) / 2 - size * 0.1
    done = typed >= total
    last = (None, None, None)
    consumed = 0
    for n, ln in enumerate(lines):
        shown = ln[:max(0, typed - consumed)]
        consumed += len(ln) + 1
        tw = font.getlength(ln)
        x, y = (W * S - tw) / 2, y0 + n * size * 1.25
        d.text((x, y), shown, font=font, fill=INK)
        if shown and len(shown) < len(ln) or (shown and n == len(lines) - 1):
            last = (x + font.getlength(shown), y, tw)
        if n == len(lines) - 1:
            line_x, line_y, line_w = x, y, tw
    if not done and int(u * 6) % 2 == 0 and last[0] is not None:  # cursor piscando enquanto escreve
        cx, cy, _ = last
        d.rectangle((cx + 4 * S, cy + size * 0.1, cx + 4 * S + size * 0.08, cy + size * 1.0), fill=INK)
    if done:  # sublinhado ondulado que aparece depois
        k = min(1.0, (u - total / 16) / 0.4)
        pts = [(line_x + i * line_w / 60, line_y + size * 1.22 + 4 * S * math.sin(i / 3.0)) for i in range(int(61 * k))]
        if len(pts) > 1:
            d.line(pts, fill=INK, width=max(2, round(4 * S)), joint='curve')


def render(spec: dict, W: int, Hpx: int, u: float, font_path=None) -> Image.Image:
    """Painel (RGBA, W x Hpx) da ilustração `spec` `u` segundos depois de aparecer."""
    S = Hpx / DESIGN_H
    dw, dh = W / S, float(DESIGN_H)
    inner = Image.new('RGBA', (W, Hpx), PAPER + (255,))
    pen = _Pen(inner, S)
    kind = spec.get('type')
    if kind == 'ninja_water':
        _ninja_water(pen, dw, dh, u)
    elif kind == 'hero_hit':
        _hero_hit(pen, dw, dh, u, font_path)
    elif kind == 'formula':
        _formula(pen, dw, dh, u, font_path)
        _text_formula(inner, S, dw, dh, u, str(spec.get('text', '')), font_path)
    mask = Image.new('L', (W, Hpx), 0)
    bubble = spec.get('frame') == 'bubble'
    shape = (lambda d, **kw: d.ellipse((0, 0, W - 1, Hpx - 1), **kw)) if bubble else \
        (lambda d, **kw: d.rounded_rectangle((0, 0, W - 1, Hpx - 1), radius=int(28 * S), **kw))
    shape(ImageDraw.Draw(mask), fill=255)
    out = Image.new('RGBA', (W, Hpx), (0, 0, 0, 0))
    out.paste(inner, (0, 0), mask)
    shape(ImageDraw.Draw(out), outline=INK, width=max(2, round(7 * S)))
    return out
