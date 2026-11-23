"""Bonecos animados ("cartum"): personagens desenhados por código, sem IA e sem custo por vídeo.

Peças independentes (trocar uma não exige mexer nas outras):
  - `draw_character()`   desenha UM personagem a partir de uma "ficha" (cabelo, cores, óculos) e de uma pose;
  - `Actor`              transforma fala, emoção e gesto em poses ao longo do tempo (boca sincronizada com as
                         palavras, piscar, olhar, balanço, gestos);
  - `Stage`              cenário + personagens + câmera; gera os quadros de uma cena.
Os personagens não conhecem o cenário nem a narração: só recebem os tempos das palavras.
"""
from __future__ import annotations

import math
import re
import unicodedata
import zlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

INK = (22, 22, 22)
PAPER = (250, 250, 250)

# brow: -1 brava ... +1 triste | lid: pálpebra caída (0..1) | lift: sobrancelhas erguidas | eye: tamanho do olho
EMOTIONS = {
    'neutral': dict(brow=0.15, lid=0.0, lift=0.0, eye=1.0, mouth='flat'),
    'happy': dict(brow=0.35, lid=0.0, lift=4.0, eye=1.0, mouth='smile'),
    'angry': dict(brow=-0.9, lid=0.3, lift=0.0, eye=0.95, mouth='frown'),
    'sad': dict(brow=0.9, lid=0.3, lift=0.0, eye=1.0, mouth='frown'),
    'surprised': dict(brow=0.2, lid=0.0, lift=16.0, eye=1.28, mouth='flat'),
    'thinking': dict(brow=-0.3, lid=0.25, lift=2.0, eye=1.0, mouth='flat', look=(0.55, 0.7)),
    'smug': dict(brow=-0.4, lid=0.5, lift=0.0, eye=1.0, mouth='smile'),
}
GESTURES = ('none', 'point', 'hip', 'open', 'shrug')
# Planos: wide = os dois | speaker = plano médio de quem fala | reaction = close em quem ESCUTA
CAMERAS = ('auto', 'wide', 'speaker', 'reaction')
# Quem escuta também age: gesto leve conforme a reação (depois de um pequeno atraso)
REACTION_GESTURE = {'surprised': 'shrug', 'smug': 'hip', 'angry': 'hip', 'thinking': 'hip'}
REACT_DELAY = 0.45  # segundos até o ouvinte reagir ao que ouviu
HAIRS = ('none', 'ponytail', 'bob', 'spiky', 'short')
# Roupa e acessórios são da FICHA do personagem (independentes do cenário e da fala): `outfit` troca o tronco,
# `accessories` soma peças. `preset` aplica um conjunto pronto (o que a ficha disser por cima prevalece).
OUTFITS = ('casual', 'scrubs', 'coat')
ACCESSORIES = ('stethoscope', 'badge', 'pen')
PRESETS = {
    'nurse': {'outfit': 'scrubs', 'accessories': ['stethoscope', 'badge', 'pen'], 'hair': 'short',
              'hair_color': [30, 30, 30], 'shirt': [104, 104, 104], 'pants': [118, 118, 118], 'glasses': False},
}
BACKGROUNDS = ('room', 'plain')
SIDES = ('left', 'right')
MAX_CHARACTERS = 2

# Pontos do braço (x para frente, y para cima, em unidades do desenho): (controle, mão) do braço da frente e do de trás
_ARMS = {
    'down': ((84, 280), (60, 190), (-84, 280), (-60, 190)),
    'hip': ((120, 280), (42, 205), (-120, 280), (-42, 205)),
    'point': ((120, 400), (165, 510), (-84, 280), (-60, 190)),
    'open': ((105, 330), (175, 300), (-105, 330), (-175, 300)),
    'shrug': ((100, 300), (112, 375), (-100, 300), (-112, 375)),
}
_DEFAULT_LOOKS = [
    {'hair': 'ponytail', 'hair_color': [62, 62, 62], 'shirt': [236, 236, 236], 'pants': [200, 200, 200], 'glasses': False},
    {'hair': 'spiky', 'hair_color': [28, 28, 28], 'shirt': [112, 112, 112], 'pants': [170, 170, 170], 'glasses': True},
]


def character_spec(cid: str, raw: dict | None, index: int) -> dict:
    """Ficha completa do personagem: o que o roteiro não disser usa os padrões (aparência diferente por posição)."""
    spec = dict(_DEFAULT_LOOKS[index % len(_DEFAULT_LOOKS)])
    spec.update(PRESETS.get((raw or {}).get('preset'), {}))
    spec.update({k: v for k, v in (raw or {}).items() if v is not None})
    spec.setdefault('outfit', 'casual')
    spec.setdefault('accessories', [])
    spec.setdefault('side', 'left' if index == 0 else 'right')
    spec.setdefault('name', cid)
    return spec


def validate_toon(toon) -> None:
    """Levanta ValueError (mensagem em português) se o bloco "toon" do roteiro estiver errado."""
    if not isinstance(toon, dict):
        raise ValueError('"toon" deve ser um objeto com "characters" (e, opcional, "background").')
    chars = toon.get('characters')
    if not isinstance(chars, dict) or not chars:
        raise ValueError('"toon.characters" precisa ter pelo menos um personagem.')
    if len(chars) > MAX_CHARACTERS:
        raise ValueError(f'No momento são aceitos até {MAX_CHARACTERS} personagens ("toon.characters").')
    bg = toon.get('background', 'room')
    if not isinstance(bg, str) or not bg:
        raise ValueError('"toon.background" deve ser "room", "plain" ou o caminho de uma imagem.')
    for cid, raw in chars.items():
        if not isinstance(raw, dict):
            raise ValueError(f'Personagem "{cid}": deve ser um objeto.')
        if raw.get('hair', 'none') not in HAIRS:
            raise ValueError(f'Personagem "{cid}": "hair" deve ser ' + ', '.join(HAIRS) + '.')
        if raw.get('preset') is not None and raw['preset'] not in PRESETS:
            raise ValueError(f'Personagem "{cid}": "preset" deve ser ' + ', '.join(PRESETS) + '.')
        if raw.get('outfit', 'casual') not in OUTFITS:
            raise ValueError(f'Personagem "{cid}": "outfit" deve ser ' + ', '.join(OUTFITS) + '.')
        acc = raw.get('accessories', [])
        if not isinstance(acc, list) or any(a not in ACCESSORIES for a in acc):
            raise ValueError(f'Personagem "{cid}": "accessories" deve ser uma lista com ' + ', '.join(ACCESSORIES) + '.')
        if raw.get('side', 'left') not in SIDES:
            raise ValueError(f'Personagem "{cid}": "side" deve ser left ou right.')
        voice = raw.get('voice')
        if voice is not None and not re.fullmatch(r'[a-z]{2}-[A-Z]{2}-[A-Za-z]+Neural', str(voice)):
            raise ValueError(f'Personagem "{cid}": "voice" inválida (ex.: pt-BR-FranciscaNeural).')
        for key in ('hair_color', 'shirt', 'pants'):
            val = raw.get(key)
            if val is not None and not (isinstance(val, list) and len(val) == 3 and all(
                    isinstance(c, int) and not isinstance(c, bool) and 0 <= c <= 255 for c in val)):
                raise ValueError(f'Personagem "{cid}": "{key}" deve ser [R, G, B] (0 a 255).')


def validate_scene(scene: dict, toon: dict | None, n: int) -> None:
    """Valida os campos de uma cena de cartum (speaker, emotion, reaction, gesture, camera)."""
    chars = (toon or {}).get('characters') or {}
    speaker = scene.get('speaker')
    if not isinstance(speaker, str) or not speaker:
        raise ValueError(f'Cena {n}: "speaker" deve ser o nome de um personagem de "toon.characters".')
    if not chars:
        raise ValueError(f'Cena {n}: cena de cartum precisa do bloco "toon" com os personagens no roteiro.')
    if speaker not in chars:
        raise ValueError(f'Cena {n}: "speaker" "{speaker}" não existe em "toon.characters" ({", ".join(chars)}).')
    for key in ('emotion', 'reaction'):
        if scene.get(key, 'neutral') not in EMOTIONS:
            raise ValueError(f'Cena {n}: "{key}" deve ser ' + ', '.join(EMOTIONS) + '.')
    if scene.get('gesture', 'none') not in GESTURES:
        raise ValueError(f'Cena {n}: "gesture" deve ser ' + ', '.join(GESTURES) + '.')
    if scene.get('camera', 'auto') not in CAMERAS:
        raise ValueError(f'Cena {n}: "camera" deve ser ' + ', '.join(CAMERAS) + '.')
    if scene.get('demo') not in (None, '', False):
        from . import toon_props
        toon_props.validate_demo(scene.get('demo'), scene.get('demo_at'), n)
        if scene.get('camera', 'auto') not in ('auto', 'wide'):
            raise ValueError(f'Cena {n}: "demo" aparece na parede e precisa do plano aberto ("camera": "wide" ou "auto").')


# ------------------------------------------------------------------ desenho

def _bezier(p0, p1, p2, n=22):
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]) for t in (i / n for i in range(n + 1))]


def _lerp(a, b, t):
    return a + (b - a) * t


class _Ink:
    """Camada transparente onde se desenha em 'unidades' (x para a direita, y para cima, pés em y=0)."""

    def __init__(self, size, k, ax, ay):
        self.img = Image.new('RGBA', size, (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)
        self.k, self.ax, self.ay = k, ax, ay
        self.rot, self.pivot = 0.0, (0.0, 0.0)  # inclinação (graus, anti-horário) em torno de `pivot`: usada na cabeça

    def p(self, x, y):
        if self.rot:
            a = math.radians(self.rot)
            dx, dy = x - self.pivot[0], y - self.pivot[1]
            x = self.pivot[0] + dx * math.cos(a) - dy * math.sin(a)
            y = self.pivot[1] + dx * math.sin(a) + dy * math.cos(a)
        return (self.ax + x * self.k, self.ay - y * self.k)

    def lw(self, w):
        return max(1, round(w * self.k))

    def ellipse(self, cx, cy, rx, ry, fill=None, outline=INK, w=5):
        if self.rot and abs(rx - ry) > 0.5:  # elipse inclinada: vira polígono (o PIL não gira elipses)
            pts = [(cx + rx * math.cos(2 * math.pi * i / 40), cy + ry * math.sin(2 * math.pi * i / 40)) for i in range(40)]
            return self.poly(pts, fill=fill, outline=outline, w=w)
        x, y = self.p(cx, cy)
        self.d.ellipse((x - rx * self.k, y - ry * self.k, x + rx * self.k, y + ry * self.k), fill=fill,
                       outline=outline, width=self.lw(w) if outline else 0)

    def poly(self, pts, fill=None, outline=INK, w=5):
        P = [self.p(x, y) for x, y in pts]
        self.d.polygon(P, fill=fill)
        if outline:
            self.d.line(P + [P[0]], fill=outline, width=self.lw(w), joint='curve')

    def line(self, pts, w, fill=INK):
        P = [self.p(x, y) for x, y in pts]
        self.d.line(P, fill=fill, width=self.lw(w), joint='curve')
        r = self.lw(w) / 2
        for x, y in (P[0], P[-1]):
            self.d.ellipse((x - r, y - r, x + r, y + r), fill=fill)

    def noodle(self, pts, w, fill):
        """Membro 'macarrão': contorno preto + miolo colorido, pontas arredondadas."""
        self.line(pts, w + 9, INK)
        self.line(pts, w, fill)

    def rrect(self, x0, y0, x1, y1, r, fill):
        a, b = self.p(x0, y1), self.p(x1, y0)
        self.d.rounded_rectangle((a[0], a[1], b[0], b[1]), radius=int(r * self.k), fill=fill, outline=INK,
                                 width=self.lw(5))


def _arc_points(cx, cy, rx, ry, a0, a1, n=24):
    return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def _lid(ink, cx, cy, r, frac):
    """Pálpebra: cobre a parte de cima do olho até `frac` do diâmetro."""
    if frac <= 0.02:
        return
    line_y = cy + r - frac * 2 * r  # y (para cima) onde a pálpebra termina
    s0 = max(-1.0, min(1.0, (line_y - cy) / r))
    a_hi = math.degrees(math.asin(s0))  # ângulo da interseção
    pts = _arc_points(cx, cy, r, r, a_hi, 180 - a_hi, 20)
    ink.poly(pts, fill=(208, 208, 208), outline=INK, w=4)


def _dress(ink, spec: dict, top: float, c: float, shirt) -> None:
    """Roupa (`outfit`) e acessórios por cima do tronco. `c` = deslocamento horizontal do tronco."""
    outfit, acc = spec.get('outfit', 'casual'), spec.get('accessories') or []
    dark = sum(shirt) / 3 < 150 and outfit != 'coat'  # peças finas precisam contrastar com a roupa
    thin = PAPER if dark else INK
    if outfit == 'scrubs':  # pijama cirúrgico: gola em V e bolso no peito
        ink.poly([(c - 24, top), (c + 24, top), (c, top - 46)], fill=PAPER, outline=INK, w=4)
        ink.rrect(c - 38, top - 100, c - 12, top - 66, 7, shirt)
    elif outfit == 'coat':  # jaleco branco, mais longo que a camisa, com lapela e fenda
        ink.rrect(c - 49, 112, c + 49, top, 30, PAPER)
        ink.poly([(c - 20, top), (c + 20, top), (c, top - 52)], fill=shirt, outline=INK, w=4)
        ink.line([(c - 20, top), (c - 7, top - 56), (c, top - 70)], 5)
        ink.line([(c + 20, top), (c + 7, top - 56), (c, top - 70)], 5)
        ink.line([(c, top - 70), (c, 112)], 4)
    if 'stethoscope' in acc:  # em volta do pescoço; a peça do peito pende na frente
        ink.line(_bezier((c - 27, top + 2), (c - 38, top - 96), (c, top - 112)), 5, thin)
        ink.line(_bezier((c + 27, top + 2), (c + 38, top - 96), (c, top - 112)), 5, thin)
        ink.ellipse(c, top - 118, 12, 12, fill=(70, 70, 70), outline=thin, w=4)
    if 'badge' in acc:  # crachá sem marca: foto e linha de texto
        ink.line([(c + 27, top - 52), (c + 27, top - 62)], 3)
        ink.rrect(c + 14, top - 112, c + 40, top - 62, 5, PAPER)
        ink.ellipse(c + 27, top - 80, 6, 6, fill=INK, outline=None)
        ink.line([(c + 20, top - 98), (c + 34, top - 98)], 3)
    if 'pen' in acc:  # caneta no bolso
        ink.line([(c - 25, top - 66), (c - 25, top - 92)], 4, thin)


def draw_character(spec: dict, pose: dict, k: float, size=(640, 800), facing: int = 1) -> Image.Image:
    """Desenha um personagem numa camada RGBA (pés no centro da base). `k` = pixels por unidade do desenho."""
    W, H = int(size[0] * k), int(size[1] * k)
    ink = _Ink((W, H), k, W / 2, H * 0.965)
    bob, lean = pose.get('bob', 0.0), pose.get('lean', 0.0)
    shirt, pants = tuple(spec['shirt']), tuple(spec['pants'])
    hair_col = tuple(spec['hair_color'])
    ink.ellipse(0, -3, 74, 11, fill=(188, 188, 188), outline=None)  # sombra no chão
    # pernas
    ink.noodle(_bezier((-14, 195), (-20, 100), (-18, 4)), 21, pants)
    ink.noodle(_bezier((14, 195), (24, 100), (42, 4)), 21, pants)
    # corpo (tubo) com o balanço da respiração
    top, bot = 380 + bob * 0.6, 168
    ink.rrect(-43 + lean * 0.5, bot, 43 + lean * 0.5, top, 36, shirt)
    _dress(ink, spec, top, lean * 0.5, shirt)
    # braços (mistura de dois gestos)
    g1, g2, a = pose.get('gesture', ('down', 'down', 0.0))
    A, B = _ARMS[g1], _ARMS[g2]

    osc = pose.get('arm_osc', (0.0, 0.0))  # vaivém contínuo das mãos (braço de trás, braço da frente): nada fica "congelado"
    for sign, ci, hi in ((-1, 2, 3), (1, 0, 1)):  # braço de trás primeiro, da frente por cima
        o = osc[0] if sign < 0 else osc[1]
        sx, sy = sign * 36 + lean * 0.5, top - 40
        ctrl = (_lerp(A[ci][0], B[ci][0], a) + lean * 0.5 + o * 0.4, _lerp(A[ci][1], B[ci][1], a) + bob * 0.6 + o * 0.7)
        hand = (_lerp(A[hi][0], B[hi][0], a) + lean * 0.5 + o * 0.8, _lerp(A[hi][1], B[hi][1], a) + bob * 0.6 + o * 1.2)
        ink.noodle(_bezier((sx, sy), ctrl, hand), 17, PAPER)
        ink.ellipse(hand[0], hand[1], 13, 13, fill=PAPER, outline=INK, w=5)
    # cabeça (inclina e acena em torno da base do pescoço)
    emo = pose['emotion']
    hx, hy, rx, ry = lean, top + 128 + bob + pose.get('nod', 0.0), 118, 128
    ink.rot, ink.pivot = pose.get('tilt', 0.0), (hx, hy - ry)
    if spec['hair'] == 'ponytail':
        ink.ellipse(hx - rx * 1.08, hy + ry * 0.45, 40, 46, fill=hair_col)
    elif spec['hair'] == 'bob':
        ink.ellipse(hx, hy + 8, rx * 1.12, ry * 1.04, fill=hair_col)
    ink.ellipse(hx, hy, rx, ry, fill=PAPER, outline=INK, w=6)
    # olhos
    eye = emo['eye']
    look = pose.get('look', (0.0, 0.0))
    blink = pose.get('blink', 0.0)
    for ex in (-1, 1):
        ox, oy, er = hx + ex * 0.38 * rx, hy + 6, 40 * eye
        if blink > 0.86:
            ink.line([(ox - er, oy), (ox + er, oy)], 7, INK)
        else:
            ink.ellipse(ox, oy, er, er, fill=PAPER, outline=INK, w=5)
            pr = 0.34 * er
            ink.ellipse(ox + look[0] * 0.5 * er, oy + look[1] * 0.45 * er, pr, pr, fill=INK, outline=None)
            _lid(ink, ox, oy, er, max(emo['lid'], blink))
        # sobrancelha: ponta de dentro e ponta de fora
        by = oy + er + 17 + emo['lift']
        inner = (ox - ex * er * 0.9, by + emo['brow'] * 22)
        outer = (ox + ex * er * 1.0, by - emo['brow'] * 10)
        ink.line([inner, outer], 8, INK)
        if spec.get('glasses'):
            ink.ellipse(ox, oy, er + 4, er + 4, fill=None, outline=INK, w=5)
    if spec.get('glasses'):
        ink.line([(hx - 0.38 * rx + 44, hy + 6), (hx + 0.38 * rx - 44, hy + 6)], 5, INK)
    # boca
    my, m = hy - ry * 0.5, pose.get('mouth', 0.0)
    mw = 31 * pose.get('mouth_w', 1.0)  # "o"/"u" = boca redonda e estreita; "i"/"e" = larga
    if m > 0.08:
        mh = 12 + 46 * m
        ink.ellipse(hx, my, mw, mh / 2, fill=(40, 40, 40), outline=INK, w=5)
        if mh > 24:
            ink.ellipse(hx, my - mh * 0.22, mw * 0.55, mh * 0.2, fill=(196, 128, 128), outline=None)
    elif emo['mouth'] == 'smile':
        ink.line(_arc_points(hx, my + 14, 34, 22, 205, 335, 14), 6, INK)
    elif emo['mouth'] == 'frown':
        ink.line(_arc_points(hx, my - 16, 30, 16, 25, 155, 14), 6, INK)
    else:
        ink.line([(hx - 24, my), (hx + 24, my)], 6, INK)
    # cabelo (frente): só o topo da cabeça, deixando testa e sobrancelhas à mostra
    if spec['hair'] in ('ponytail', 'bob'):
        ink.poly(_arc_points(hx, hy, rx * 1.0, ry * 1.0, 42, 138, 20), fill=hair_col, outline=INK, w=5)
        ink.poly([(hx - rx * 0.66, hy + ry * 0.74), (hx - rx * 0.1, hy + ry * 0.52), (hx + rx * 0.42, hy + ry * 0.72)],
                 fill=hair_col, outline=INK, w=4)  # franja
    elif spec['hair'] == 'short':  # cabelo curto e simples: uma "touca" sobre o topo, com a testa à mostra
        ink.poly(_arc_points(hx, hy, rx * 1.02, ry * 1.04, 28, 152, 24) + [(hx + rx * 0.62, hy + ry * 0.72),
                                                                       (hx, hy + ry * 0.60), (hx - rx * 0.62, hy + ry * 0.72)],
                 fill=hair_col, outline=INK, w=5)
    elif spec['hair'] == 'spiky':
        pts = [(hx + rx * 0.97 * math.cos(math.radians(142)), hy + ry * 0.97 * math.sin(math.radians(142)))]
        for i in range(5):
            a0, a1 = 142 - i * 21, 142 - (i + 1) * 21
            pts.append((hx + rx * 1.25 * math.cos(math.radians((a0 + a1) / 2)),
                        hy + ry * 1.40 * math.sin(math.radians((a0 + a1) / 2))))
            pts.append((hx + rx * 0.97 * math.cos(math.radians(a1)), hy + ry * 0.97 * math.sin(math.radians(a1))))
        ink.poly(pts, fill=hair_col, outline=INK, w=5)
    layer = ink.img
    return ImageOps.mirror(layer) if facing < 0 else layer


# ------------------------------------------------------------------ animação

def _hash01(*parts) -> float:
    return (zlib.crc32('|'.join(map(str, parts)).encode('utf-8')) % 1000) / 1000.0


_VOWELS = r'[aeiouyáéíóúâêôãõàü]+'
# abertura e largura da boca por vogal: "a" abre muito; "o"/"u" arredondam (estreita); "i"/"e" alargam
_V_OPEN = {'a': 1.0, 'e': 0.85, 'i': 0.7, 'o': 0.9, 'u': 0.75, 'y': 0.7}
_V_WIDTH = {'a': 1.0, 'e': 1.08, 'i': 1.22, 'o': 0.62, 'u': 0.55, 'y': 1.15}


def _base_vowel(ch: str) -> str:
    base = unicodedata.normalize('NFD', ch)[0]
    return base if base in _V_OPEN else 'a'


def mouth_shape(words, t: float, seed: str = '') -> tuple[float, float]:
    """(abertura 0..1, largura relativa) da boca no instante t. A boca abre e fecha a cada sílaba de cada palavra falada,
    com a forma da vogal daquela sílaba; fecha de verdade nas pausas entre palavras e frases."""
    for i, w in enumerate(words):
        if w.start - 0.03 <= t <= w.end + 0.04:
            groups = re.findall(_VOWELS, w.text.lower()) or ['a']
            span = max(0.09, w.end - w.start)
            phase = (t - w.start) / span * len(groups)
            vowel = _base_vowel(groups[min(len(groups) - 1, max(0, int(phase)))][0])
            amp = (0.62 + 0.38 * _hash01(seed, i, w.text)) * _V_OPEN[vowel]
            return amp * (0.5 - 0.5 * math.cos(2 * math.pi * phase)), _V_WIDTH[vowel]
    return 0.0, 1.0


def mouth_open(words, t: float, seed: str = '') -> float:
    """Só a abertura da boca (0..1): ver `mouth_shape`."""
    return mouth_shape(words, t, seed)[0]


def _ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


class Actor:
    """Pose de um personagem ao longo de uma cena. `words`: palavras que ELE fala (vazio = está ouvindo)."""

    def __init__(self, cid, spec, words, emotion='neutral', gesture='none', seed=0, heard=()):
        self.cid, self.spec, self.words = cid, spec, list(words)
        self.heard = list(heard)  # palavras do OUTRO personagem (só o ouvinte usa): a reação silenciosa acompanha a fala
        self.emotion_name = emotion if emotion in EMOTIONS else 'neutral'
        self.gesture = gesture if gesture in GESTURES else 'none'
        self.seed = f'{cid}{seed}'
        self.speaking = bool(self.words)
        # piscadas em intervalos "irregulares" (determinísticos)
        self.blinks, t, n = [], 0.5 + 1.6 * _hash01(self.seed, 'b0'), 0
        while t < 120:
            self.blinks.append(t)
            n += 1
            t += 2.2 + 2.4 * _hash01(self.seed, 'b', n)

    def _emotion(self, t):
        target = EMOTIONS[self.emotion_name]
        base = EMOTIONS['neutral']
        a = _ease(t / 0.22)
        out = {k: (_lerp(base[k], target[k], a) if isinstance(base[k], (int, float)) else (target[k] if a > 0.4 else base[k]))
               for k in base}
        return out

    def _blink(self, t):
        """Fecha rápido (0,05 s), fica fechado (0,06 s) e abre (0,07 s): o trecho fechado garante que pelo
        menos um quadro mostre o olho de fato fechado, mesmo a 24 ou 30 quadros por segundo."""
        for b in self.blinks:
            if b <= t <= b + 0.18:
                x = t - b
                return max(0.0, min(1.0, x / 0.05, (0.18 - x) / 0.07))
        return 0.0

    def _stress(self, t, words=None):
        """0..1: pico de ênfase a cada 3 palavras (gesto de braço, aceno e inclinação de cabeça)."""
        pulse = 0.0
        for i, w in enumerate(self.words if words is None else words):
            if i % 3 == 0 and w.start - 0.05 <= t <= w.start + 0.7:
                x = (t - w.start + 0.05) / 0.75
                pulse = max(pulse, math.sin(math.pi * min(1.0, max(0.0, x))))
        return pulse

    def _gesture(self, t):
        if not self.speaking:
            name = REACTION_GESTURE.get(self.emotion_name)  # o ouvinte reage com o corpo, depois de um instante
            if name:
                return ('down', name, 0.8 * _ease((t - REACT_DELAY) / 0.5))
            return ('down', 'down', 0.0)
        if self.gesture != 'none':
            sway = 0.09 * math.sin(2 * math.pi * 0.9 * t) * _ease(t / 0.6)
            return ('down', self.gesture, min(1.0, _ease(t / 0.45) + sway))
        return ('down', 'open', 0.75 * self._stress(t))

    def pose(self, t: float) -> dict:
        ph = _hash01(self.seed, 'ph') * 2 * math.pi
        if self.speaking:
            emo = self._emotion(t)
            m, mw = mouth_shape(self.words, t, self.seed)
            stress = self._stress(t)
            look = (0.45 + 0.25 * math.sin(1.1 * t + _hash01(self.seed, 'l') * 6), 0.12 * math.sin(0.8 * t))
            bob = 5 * abs(math.sin(2 * math.pi * 2.0 * t)) * (0.35 + m)
            lean = 7 * _ease(t / 0.4) + 4 * math.sin(2 * math.pi * 0.7 * t + ph)  # o tronco balança enquanto fala
            tilt = 3.0 * math.sin(2 * math.pi * 0.55 * t + ph) + 5.0 * stress      # cabeça inclina na palavra de destaque
            nod = -9.0 * stress + 2.0 * m                                           # e acena
            osc = (8 * math.sin(2 * math.pi * 0.9 * t + ph), 8 * math.sin(2 * math.pi * 1.1 * t + ph + 1.3))
        else:
            emo = self._emotion(max(0.0, t - REACT_DELAY))
            m, mw = 0.0, 1.0
            step = int(t / 1.3)  # o ouvinte olha para quem fala, com pequenos desvios a cada ~1,3 s
            look = (0.85 + 0.12 * (_hash01(self.seed, 'x', step) - 0.5), 0.2 * (_hash01(self.seed, 'y', step) - 0.5))
            bob = 2.5 * math.sin(2 * math.pi * 0.45 * t + ph)
            r = _ease((t - REACT_DELAY) / 0.5)
            lean = 3 * math.sin(2 * math.pi * 0.3 * t + ph)
            tilt = 2.5 * math.sin(2 * math.pi * 0.35 * t + ph) + (4.0 if self.emotion_name != 'neutral' else 0.0) * r
            cyc = (t + _hash01(self.seed, 'n') * 2.4) % 2.4  # acena (concorda) duas vezes a cada ~2,4 s
            nod = -6.0 * max(0.0, math.sin(2 * math.pi * cyc / 0.9)) if cyc < 0.9 else 0.0
            heard = self._stress(t, self.heard) if self.heard else 0.0  # o outro enfatizou uma palavra
            nod += -6.0 * heard
            tilt += 3.0 * heard
            emo = dict(emo, lift=emo['lift'] + 5.0 * heard)
            osc = (3 * math.sin(2 * math.pi * 0.5 * t + ph), 3 * math.sin(2 * math.pi * 0.6 * t + ph + 2.0))
        if 'look' in EMOTIONS[self.emotion_name]:
            a = _ease(t / 0.3)
            tl = EMOTIONS[self.emotion_name]['look']
            look = (_lerp(look[0], tl[0], a), _lerp(look[1], tl[1], a))
        return {'emotion': emo, 'mouth': m, 'mouth_w': mw, 'blink': self._blink(t), 'look': look, 'bob': bob,
                'lean': lean, 'tilt': tilt, 'nod': nod, 'arm_osc': osc, 'gesture': self._gesture(t)}


# ------------------------------------------------------------------ cenário e câmera

def draw_room(w: int, h: int, ss: int = 2, style: str = 'room') -> Image.Image:
    """Cenário em preto e branco, com piso em perspectiva (ou liso, com 'plain')."""
    S = ss
    img = Image.new('RGB', (w * S, h * S), (236, 236, 236))
    d = ImageDraw.Draw(img)
    floor_y = h * 0.70
    if style == 'plain':
        d.rectangle((0, 0, w * S, floor_y * S), fill=(244, 244, 244))
        d.rectangle((0, floor_y * S, w * S, h * S), fill=(226, 226, 226))
        d.line((0, floor_y * S, w * S, floor_y * S), fill=(150, 150, 150), width=3 * S)
        return img
    corner = w * 0.46
    d.polygon([(0, 0), (corner * S, 0), (corner * S, (floor_y - 90) * S), (0, floor_y * S + 60 * S)], fill=(247, 247, 247))
    d.line((corner * S, 0, corner * S, (floor_y - 90) * S), fill=(120, 120, 120), width=4 * S)
    d.polygon([(0, (floor_y + 60) * S), (corner * S, (floor_y - 90) * S), (w * S, (floor_y - 30) * S), (w * S, h * S),
               (0, h * S)], fill=(224, 224, 224))
    vp = (corner * S, (floor_y - 120) * S)
    for k in range(-8, 16):  # linhas do piso que fogem para o ponto de fuga
        d.line((vp[0] + (k - 3) * 52 * S, (floor_y - 90) * S, (k * 160 - 360) * S, h * S), fill=(156, 156, 156), width=2 * S)
    for j in range(1, 8):  # linhas transversais, mais espaçadas perto da câmera
        y = (floor_y - 90) + (h - (floor_y - 90)) * (j / 8) ** 1.7
        d.line((0, (y + 70 * (j / 8)) * S, w * S, (y - 20 * (j / 8)) * S), fill=(156, 156, 156), width=2 * S)
    return img


def load_background(spec: str, w: int, h: int, ss: int, base: Path | None) -> Image.Image:
    if spec in BACKGROUNDS:
        return draw_room(w, h, ss, spec)
    path = Path(spec)
    path = path if path.is_absolute() or base is None else base / path
    if not path.is_file():
        raise FileNotFoundError(f'Cenário não encontrado: {path}')
    im = Image.open(path).convert('RGB')
    f = max(w * ss / im.width, h * ss / im.height)
    im = im.resize((math.ceil(im.width * f), math.ceil(im.height * f)), Image.Resampling.LANCZOS)
    x, y = (im.width - w * ss) // 2, (im.height - h * ss) // 2
    return im.crop((x, y, x + w * ss, y + h * ss))


def _ease_out_back(x: float) -> float:
    x = max(0.0, min(1.0, x))
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


class Stage:
    """Cenário + personagens + câmera. Gera os quadros de uma cena (`scene_frames`).

    Três planos padronizados (nunca deixam o outro personagem cortado pela metade na borda):
      wide      os dois em quadro (com um leve avanço);
      speaker   plano médio de quem fala: a janela termina antes do ouvinte;
      reaction  close em quem ESCUTA (mostra a reação enquanto o outro fala).
    Entre cenas a câmera DESLIZA do plano anterior para o novo (`GLIDE_S`), em vez de dar um corte seco."""

    GLIDE_S = 0.35
    EDGE = 150  # meia largura (unidades do desenho) da cabeça de um personagem, com cabelo

    def __init__(self, w: int, h: int, characters: dict, background: str = 'room', ss: int = 2,
                 base_dir: Path | None = None, font_path=None):
        self.w, self.h, self.ss = w, h, ss
        self.font_path = font_path
        self.chars = {cid: character_spec(cid, raw, i) for i, (cid, raw) in enumerate(characters.items())}
        self.bg = load_background(background, w, h, ss, base_dir)
        self.unit = 1.30 * min(w, h * 9 / 16) / 1080  # pixels (saída) por unidade do desenho
        self.base_y = h * 0.90  # pés baixos no quadro: sobra parede para a legenda e para a ilustração (`demo`)
        n = len(self.chars)
        self.x = {cid: w * (0.5 if n == 1 else (0.26 if spec['side'] == 'left' else 0.74)) for cid, spec in self.chars.items()}

    # ---- câmera

    def _listener(self, speaker):
        others = [c for c in self.chars if c != speaker]
        return others[0] if others else None

    def _half_widths(self, speaker):
        """(meia largura do plano do falante, do close de reação) em pixels, para o ouvinte ficar FORA do quadro."""
        listener = self._listener(speaker)
        if listener is None:
            return self.w / 3.0, self.w / 3.0 / 1.2
        dist = abs(self.x[speaker] - self.x[listener])
        half_s = max(dist - self.EDGE * self.unit - 0.02 * self.w, 0.25 * self.w)
        half_r = max(0.9 * half_s / 1.2, 205 * self.unit)  # close: mais apertado, mas com o cabelo inteiro (e folga p/ a inclinação)
        return half_s, half_r

    def _rect(self, mode, speaker, progress):
        """Retângulo (pixels de saída, sem o supersampling) que a câmera enquadra, com `progress` de 0 a 1 na cena."""
        w, h = self.w, self.h
        listener = self._listener(speaker)
        if mode == 'wide' or (listener is None and mode == 'reaction'):
            zoom, cx, cy = 1.0 + 0.04 * progress, w / 2, h * 0.5
            cw, ch = w / zoom, h / zoom
            cx = min(max(cx, cw / 2), w - cw / 2)
        else:
            subject, absent = (listener, speaker) if mode == 'reaction' else (speaker, listener)
            half = self._half_widths(speaker)[1 if mode == 'reaction' else 0]
            cw = 2 * half / (1 + (0.04 if mode == 'reaction' else 0.05) * progress)
            cy_units = 520 if mode == 'reaction' else 430
            cx = self.x[subject]
            if absent is not None:  # a janela termina antes do personagem ausente, mesmo na borda do cenário
                gap = self.EDGE * self.unit + 0.02 * w
                if self.x[absent] > cx:
                    lim = self.x[absent] - gap
                    cw = min(cw, lim)
                    cx = max(min(cx, lim - cw / 2), cw / 2)
                else:
                    lim = self.x[absent] + gap
                    cw = min(cw, w - lim)
                    cx = min(max(cx, lim + cw / 2), w - cw / 2)
            cx = min(max(cx, cw / 2), w - cw / 2)
            ch = cw * h / w
            cy = self.base_y - cy_units * self.unit
        if mode == 'wide' or (listener is None and mode == 'reaction'):
            cy = h * 0.5
        cy = min(max(cy, ch / 2), h - ch / 2)
        return (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)

    def _camera(self, mode, speaker, t, total, prev=None):
        """Retângulo (em pixels do canvas ampliado) no instante t. `prev` = (plano, falante) da cena anterior:
        nos primeiros `GLIDE_S` segundos a câmera desliza dele até o plano atual."""
        rect = self._rect(mode, speaker, t / max(total, 1e-6))
        if prev is not None and t < self.GLIDE_S:
            a = _ease(t / self.GLIDE_S)
            old = self._rect(prev[0], prev[1], 1.0)
            rect = tuple(_lerp(o, n, a) for o, n in zip(old, rect))
        return tuple(v * self.ss for v in rect)

    # ---- atores e ilustração na parede

    def scene_actors(self, speaker, words, emotion='neutral', reaction='neutral', gesture='none', seed=0):
        actors = {}
        for cid, spec in self.chars.items():
            if cid == speaker:
                actors[cid] = Actor(cid, spec, words, emotion, gesture, seed)
            else:
                actors[cid] = Actor(cid, spec, [], reaction, 'none', seed, heard=words)
        return actors

    def panel_box(self, frame='screen'):
        """Onde a "tela" da parede fica (pixels de saída): entre a legenda do topo e a cabeça dos personagens.
        O balão de pensamento (`bubble`) é mais alto: pode passar por trás das cabeças (os personagens são desenhados por cima)."""
        w, h = self.w, self.h
        head_top = self.base_y - 700 * self.unit  # inclui as pontas do cabelo espetado
        top = h * (0.25 if h > w else 0.17)
        bottom = head_top + 0.05 * h if frame == 'bubble' else head_top - 0.015 * h
        ph = max(bottom - top, 0.12 * h)
        pw = min(0.86 * w, ph * (2.1 if frame == 'bubble' else 2.4))
        return (w - pw) / 2, bottom - ph, pw, ph

    def _draw_visual(self, canvas, visual, t, speaker=None):
        from . import toon_props
        spec, at = visual
        u = t - at
        if u < 0:
            return
        x, y, pw, ph = self.panel_box(spec.get('frame', 'screen'))
        S = self.ss
        panel = toon_props.render(spec, round(pw * S), round(ph * S), u, self.font_path)
        pop = _ease_out_back(u / 0.30)
        if pop < 0.999:
            f = max(0.05, pop)
            panel = panel.resize((max(2, round(panel.width * f)), max(2, round(panel.height * f))), Image.Resampling.BILINEAR)
        cx, cy = (x + pw / 2) * S, (y + ph / 2) * S
        px, py = round(cx - panel.width / 2), round(cy - panel.height / 2)
        shadow = Image.new('RGBA', panel.size, (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow)
        box = (0, 0, panel.width - 1, panel.height - 1)
        if spec.get('frame') == 'bubble':
            sd.ellipse(box, fill=(90, 90, 90, 110))
        else:
            sd.rounded_rectangle(box, radius=int(28 * panel.height / 360), fill=(90, 90, 90, 110))
        canvas.paste(shadow, (px + 10 * S, py + 12 * S), shadow)
        canvas.paste(panel, (px, py), panel)
        if spec.get('frame') == 'bubble' and speaker in self.x:  # bolinhas do balão de pensamento, da cabeça de quem fala até o balão
            hx, hy = self.x[speaker] * S, (self.base_y - 700 * self.unit) * S
            ex, ey = cx, py + panel.height
            for frac, r in ((0.16, 0.011), (0.40, 0.017), (0.68, 0.026)):
                bx, by = hx + (ex - hx) * frac, hy + (ey - hy) * frac
                rad = r * self.w * S * min(1.0, pop)
                ImageDraw.Draw(canvas).ellipse((bx - rad, by - rad, bx + rad, by + rad), fill=(252, 252, 252), outline=(22, 22, 22),
                                               width=max(2, round(0.0045 * self.w * S)))

    def frame(self, actors: dict, speaker: str, t: float, total: float, camera: str = 'speaker', prev=None,
              visual=None) -> Image.Image:
        canvas = self.bg.copy()
        k = self.unit * self.ss
        if visual:
            self._draw_visual(canvas, visual, t, speaker)
        order = sorted(self.chars, key=lambda c: (c == speaker, self.x[c]))  # quem fala fica por cima
        for cid in order:
            spec = self.chars[cid]
            facing = 1 if len(self.chars) == 1 or spec['side'] == 'left' else -1  # um olha para o outro
            layer = draw_character(spec, actors[cid].pose(t), k, facing=facing)
            px = int(self.x[cid] * self.ss - layer.width / 2)
            py = int(self.base_y * self.ss - layer.height * 0.965)
            canvas.paste(layer, (px, py), layer)
        box = self._camera(camera, speaker, t, total, prev)
        return canvas.resize((self.w, self.h), Image.Resampling.BILINEAR, box=box)

    def scene_frames(self, speaker, words, total_frames, fps, emotion='neutral', reaction='neutral', gesture='none',
                     camera='speaker', seed=0, prev=None, demo=None, demo_at=0.3):
        """Gera os quadros RGB (bytes) de uma cena. `words`: palavras de QUEM FALA, com tempos a partir do início do clipe.
        `prev`: (plano, falante) da cena anterior (a câmera desliza dele). `demo`: ilustração na parede (toon_props)."""
        actors = self.scene_actors(speaker, words, emotion, reaction, gesture, seed)
        total = total_frames / fps
        vis = None
        if demo not in (None, '', False):
            from . import toon_props
            vis = (toon_props.demo_spec(demo), float(0.3 if demo_at is None else demo_at))
        for f in range(total_frames):
            yield self.frame(actors, speaker, f / fps, total, camera, prev, vis).tobytes()
