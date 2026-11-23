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
CAMERAS = ('auto', 'wide', 'speaker')
HAIRS = ('none', 'ponytail', 'bob', 'spiky')
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
    spec.update({k: v for k, v in (raw or {}).items() if v is not None})
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

    def p(self, x, y):
        return (self.ax + x * self.k, self.ay - y * self.k)

    def lw(self, w):
        return max(1, round(w * self.k))

    def ellipse(self, cx, cy, rx, ry, fill=None, outline=INK, w=5):
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
    # braços (mistura de dois gestos)
    g1, g2, a = pose.get('gesture', ('down', 'down', 0.0))
    A, B = _ARMS[g1], _ARMS[g2]

    for sign, ci, hi in ((-1, 2, 3), (1, 0, 1)):  # braço de trás primeiro, da frente por cima
        sx, sy = sign * 36 + lean * 0.5, top - 40
        ctrl = (_lerp(A[ci][0], B[ci][0], a) + lean * 0.5, _lerp(A[ci][1], B[ci][1], a) + bob * 0.6)
        hand = (_lerp(A[hi][0], B[hi][0], a) + lean * 0.5, _lerp(A[hi][1], B[hi][1], a) + bob * 0.6)
        ink.noodle(_bezier((sx, sy), ctrl, hand), 17, PAPER)
        ink.ellipse(hand[0], hand[1], 13, 13, fill=PAPER, outline=INK, w=5)
    # cabeça
    emo = pose['emotion']
    hx, hy, rx, ry = lean, top + 128 + bob, 118, 128
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
    if m > 0.08:
        mh = 12 + 46 * m
        ink.ellipse(hx, my, 31, mh / 2, fill=(40, 40, 40), outline=INK, w=5)
        if mh > 24:
            ink.ellipse(hx, my - mh * 0.22, 17, mh * 0.2, fill=(196, 128, 128), outline=None)
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


def mouth_open(words, t: float, seed: str = '') -> float:
    """Abertura da boca (0..1) no instante t: abre e fecha a cada sílaba de cada palavra falada; fechada nas pausas."""
    for i, w in enumerate(words):
        if w.start - 0.03 <= t <= w.end + 0.04:
            syllables = max(1, len(re.findall(r'[aeiouyáéíóúâêôãõàü]+', w.text.lower())))
            span = max(0.09, w.end - w.start)
            phase = (t - w.start) / span * syllables
            amp = 0.55 + 0.45 * _hash01(seed, i, w.text)
            return amp * (0.5 - 0.5 * math.cos(2 * math.pi * phase))
    return 0.0


def _ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


class Actor:
    """Pose de um personagem ao longo de uma cena. `words`: palavras que ELE fala (vazio = está ouvindo)."""

    def __init__(self, cid, spec, words, emotion='neutral', gesture='none', seed=0):
        self.cid, self.spec, self.words = cid, spec, list(words)
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

    def _gesture(self, t):
        if not self.speaking:
            return ('down', 'down', 0.0)
        if self.gesture != 'none':
            sway = 0.06 * math.sin(2 * math.pi * 1.3 * t)
            return ('down', self.gesture, min(1.0, _ease(t / 0.3) + sway))
        pulse = 0.0  # gesto automático: braços abrem nas palavras de destaque
        for i, w in enumerate(self.words):
            if i % 3 == 0 and w.start - 0.05 <= t <= w.start + 0.7:
                x = (t - w.start + 0.05) / 0.75
                pulse = max(pulse, math.sin(math.pi * min(1.0, max(0.0, x))))
        return ('down', 'open', 0.75 * pulse)

    def pose(self, t: float) -> dict:
        emo = self._emotion(t)
        m = mouth_open(self.words, t, self.seed) if self.speaking else 0.0
        if self.speaking:
            look = (0.45 + 0.25 * math.sin(1.1 * t + _hash01(self.seed, 'l') * 6), 0.12 * math.sin(0.8 * t))
            bob = 5 * abs(math.sin(2 * math.pi * 2.0 * t)) * (0.35 + m)
            lean = 7 * _ease(t / 0.4)
        else:
            step = int(t / 1.3)  # o ouvinte olha para quem fala, com pequenos desvios a cada ~1,3 s
            look = (0.85 + 0.12 * (_hash01(self.seed, 'x', step) - 0.5), 0.2 * (_hash01(self.seed, 'y', step) - 0.5))
            bob = 2.5 * math.sin(2 * math.pi * 0.45 * t + _hash01(self.seed, 'p') * 6)
            lean = 0.0
        if 'look' in EMOTIONS[self.emotion_name]:
            a = _ease(t / 0.3)
            tl = EMOTIONS[self.emotion_name]['look']
            look = (_lerp(look[0], tl[0], a), _lerp(look[1], tl[1], a))
        return {'emotion': emo, 'mouth': m, 'blink': self._blink(t), 'look': look, 'bob': bob, 'lean': lean,
                'gesture': self._gesture(t)}


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


class Stage:
    """Cenário + personagens + câmera. Gera os quadros de uma cena (`scene_frames`)."""

    def __init__(self, w: int, h: int, characters: dict, background: str = 'room', ss: int = 2,
                 base_dir: Path | None = None):
        self.w, self.h, self.ss = w, h, ss
        self.chars = {cid: character_spec(cid, raw, i) for i, (cid, raw) in enumerate(characters.items())}
        self.bg = load_background(background, w, h, ss, base_dir)
        self.unit = 1.25 * min(w, h * 9 / 16) / 1080  # pixels (saída) por unidade do desenho
        self.base_y = h * 0.80
        n = len(self.chars)
        self.x = {cid: w * (0.5 if n == 1 else (0.29 if spec['side'] == 'left' else 0.71)) for cid, spec in self.chars.items()}

    def _camera(self, mode, speaker, t, total):
        """Retângulo (em pixels do canvas ampliado) que a câmera enquadra no instante t."""
        w, h, s = self.w, self.h, self.ss
        progress = t / max(total, 1e-6)
        if mode == 'wide':
            zoom, cx, cy = 1.0 + 0.06 * progress, w / 2, h * 0.5
        else:
            zoom = 1.5 + 0.09 * progress
            cx, cy = self.x[speaker], self.base_y - 430 * self.unit
        cw, ch = w / zoom, h / zoom
        cx = min(max(cx, cw / 2), w - cw / 2)
        cy = min(max(cy, ch / 2), h - ch / 2)
        return ((cx - cw / 2) * s, (cy - ch / 2) * s, (cx + cw / 2) * s, (cy + ch / 2) * s)

    def scene_actors(self, speaker, words, emotion='neutral', reaction='neutral', gesture='none', seed=0):
        actors = {}
        for cid, spec in self.chars.items():
            if cid == speaker:
                actors[cid] = Actor(cid, spec, words, emotion, gesture, seed)
            else:
                actors[cid] = Actor(cid, spec, [], reaction, 'none', seed)
        return actors

    def frame(self, actors: dict, speaker: str, t: float, total: float, camera: str = 'speaker') -> Image.Image:
        canvas = self.bg.copy()
        k = self.unit * self.ss
        order = sorted(self.chars, key=lambda c: (c == speaker, self.x[c]))  # quem fala fica por cima
        for cid in order:
            spec = self.chars[cid]
            facing = 1 if len(self.chars) == 1 or spec['side'] == 'left' else -1  # um olha para o outro
            layer = draw_character(spec, actors[cid].pose(t), k, facing=facing)
            px = int(self.x[cid] * self.ss - layer.width / 2)
            py = int(self.base_y * self.ss - layer.height * 0.965)
            canvas.paste(layer, (px, py), layer)
        box = self._camera(camera, speaker, t, total)
        return canvas.resize((self.w, self.h), Image.Resampling.BILINEAR, box=box)

    def scene_frames(self, speaker, words, total_frames, fps, emotion='neutral', reaction='neutral', gesture='none',
                     camera='speaker', seed=0):
        """Gera os quadros RGB (bytes) de uma cena. `words`: palavras de QUEM FALA, com tempos a partir do início do clipe."""
        actors = self.scene_actors(speaker, words, emotion, reaction, gesture, seed)
        total = total_frames / fps
        for f in range(total_frames):
            yield self.frame(actors, speaker, f / fps, total, camera).tobytes()
