"""Personagens por RECORTES (cutout): a aparência vem de imagens (criadas uma única vez, por exemplo pelo Gemini) e o
Studio as anima por código, sem gerar imagem nova a cada fala.

Uma personagem é uma PASTA da biblioteca (`<projeto>/personagens/<nome>/`) com `personagem.json` + as imagens:
  - `neutra` é o CORPO-BASE (boca fechada); `feliz`, `surpresa`, `falando` ... são o mesmo personagem com outra expressão,
    no mesmo enquadramento (as imagens precisam ficar alinhadas: o experimento do Gemini deu 0-2 px de diferença);
  - fundo de cor sólida (magenta), recortado por cor; a imagem pode ser JPEG (não precisa de transparência real).
Por quadro, `CutoutAsset.render(pose)` parte do corpo-base e: cola o rosto da expressão pedida (mistura suave), cola a BOCA
da vogal falada (abertura gradual: o recorte de boca aberta é achatado e misturado à boca fechada), pisca (achata os olhos),
inclina a cabeça (deformação suave: a cabeça gira, o ombro não) e respira/balança o corpo todo.
Os personagens desenhados por código (`toon.draw_character`) continuam existindo; o palco escolhe um ou outro pela ficha.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

MANIFEST = 'personagem.json'
ASSET_NAME = re.compile(r'[A-Za-z0-9_-]+')
# emoção do roteiro -> imagem da personagem (o manifesto pode trocar; o que faltar cai na neutra)
DEFAULT_MAP = {'neutral': 'neutra', 'happy': 'feliz', 'smug': 'feliz', 'surprised': 'surpresa', 'thinking': 'neutra',
               'sad': 'neutra', 'angry': 'neutra'}


# ------------------------------------------------------------------ recorte por cor

def magenta_alpha(im: Image.Image, soft=(60, 150)):
    """Máscara (0..255) do personagem: distância à cor REAL do fundo (medida nos cantos), com transição suave nas bordas."""
    a = np.asarray(im.convert('RGB')).astype(np.float32)
    corners = np.concatenate([a[:60, :60].reshape(-1, 3), a[:60, -60:].reshape(-1, 3)])
    bg = np.median(corners, axis=0)
    dist = np.sqrt(((a - bg) ** 2).sum(axis=2))
    lo, hi = soft
    return (np.clip((dist - lo) / (hi - lo), 0, 1) * 255).astype(np.uint8), bg


def despill(im: Image.Image, alpha: np.ndarray) -> Image.Image:
    """Tira o reflexo magenta das bordas semitransparentes (R e B acima do verde)."""
    a = np.asarray(im.convert('RGB')).astype(np.float32)
    al = alpha.astype(np.float32) / 255
    edge = (al > 0.02) & (al < 0.98)
    spill = np.clip(np.minimum(a[..., 0], a[..., 2]) - a[..., 1], 0, None) * edge * 0.9
    a[..., 0] -= spill
    a[..., 2] -= spill
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def key_image(im: Image.Image) -> Image.Image:
    alpha, _ = magenta_alpha(im)
    out = despill(im, alpha).convert('RGBA')
    out.putalpha(Image.fromarray(alpha))
    return out


# ------------------------------------------------------------------ validação e biblioteca

def validate_manifest(man, where='personagem.json') -> None:
    """Levanta ValueError (mensagem em português) se o manifesto de uma personagem estiver incompleto."""
    if not isinstance(man, dict):
        raise ValueError(f'{where}: deve ser um objeto.')
    imgs = man.get('images')
    if not isinstance(imgs, dict) or 'neutra' not in imgs or not all(isinstance(v, str) for v in imgs.values()):
        raise ValueError(f'{where}: "images" precisa ter ao menos "neutra" (o corpo-base) e nomes de arquivo.')
    size = man.get('ref_size')
    if not (isinstance(size, list) and len(size) == 2 and all(isinstance(v, int) and v > 0 for v in size)):
        raise ValueError(f'{where}: "ref_size" deve ser [largura, altura] das imagens, em pixels.')
    boxes = man.get('boxes') or {}
    for key in ('face', 'mouth'):
        b = boxes.get(key)
        if not (isinstance(b, list) and len(b) == 4 and all(isinstance(v, (int, float)) for v in b) and b[0] < b[2] and b[1] < b[3]):
            raise ValueError(f'{where}: "boxes.{key}" deve ser [x0, y0, x1, y1] em pixels da imagem de referência.')
    for key in ('eye_l', 'eye_r'):
        b = boxes.get(key)
        if b is not None and not (isinstance(b, list) and len(b) == 4 and b[0] < b[2] and b[1] < b[3]):
            raise ValueError(f'{where}: "boxes.{key}" deve ser [x0, y0, x1, y1].')


def find_asset(name: str, base_dir) -> Path:
    """Pasta da personagem na biblioteca: `<projeto>/personagens/<nome>`."""
    if not ASSET_NAME.fullmatch(str(name)):
        raise ValueError(f'Nome de personagem inválido: "{name}" (use letras, números, "_" e "-").')
    folder = Path(base_dir or '.') / 'personagens' / name
    if not (folder / MANIFEST).is_file():
        raise FileNotFoundError(f'Personagem "{name}" não encontrada: faltam {folder / MANIFEST} e as imagens '
                                f'(a biblioteca fica em "personagens/" ao lado do roteiro).')
    return folder


def _smooth(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def _feather_mask(size, feather: int) -> Image.Image:
    m = Image.new('L', size, 0)
    f = max(1, min(feather, size[0] // 2 - 1, size[1] // 2 - 1))
    ImageDraw.Draw(m).rounded_rectangle((f, f, size[0] - f, size[1] - f), radius=f, fill=255)
    return m.filter(ImageFilter.GaussianBlur(f / 2))


def _ellipse_mask(size, feather: int) -> Image.Image:
    """Elipse suave inscrita na caixa: exclui os cantos (onde o contorno da mandíbula/cabelo poderia entrar na colagem)."""
    m = Image.new('L', size, 0)
    f = max(1, min(feather, size[0] // 2 - 1, size[1] // 2 - 1))
    ImageDraw.Draw(m).ellipse((f, f, size[0] - f, size[1] - f), fill=255)
    return m.filter(ImageFilter.GaussianBlur(f / 2))


def _scale_mask(mask: Image.Image, k: float) -> Image.Image:
    return mask.point(lambda v: int(v * k))


class CutoutAsset:
    """Uma personagem carregada: imagens recortadas e escaladas para `width_px` de largura, prontas para `render`."""

    def __init__(self, folder, width_px: int | None = None, height_px: int | None = None):
        self.folder = Path(folder)
        man = json.loads((self.folder / MANIFEST).read_text(encoding='utf-8'))
        validate_manifest(man, str(self.folder / MANIFEST))
        self.name = man.get('name', self.folder.name)
        ref_w, ref_h = man['ref_size']
        if not width_px and not height_px:
            raise ValueError('CutoutAsset precisa de width_px (largura que a imagem inteira teria) ou height_px (altura da figura).')
        self.map = {**DEFAULT_MAP, **(man.get('map') or {})}
        keyed = {}
        for key, fname in man['images'].items():
            path = self.folder / fname
            if not path.is_file():
                raise FileNotFoundError(f'Imagem da personagem "{self.name}" não encontrada: {path}')
            im = Image.open(path)
            if im.size != (ref_w, ref_h):
                raise ValueError(f'"{fname}" tem {im.size[0]}x{im.size[1]}, mas "ref_size" diz {ref_w}x{ref_h}: as imagens da '
                                 'personagem precisam ter o mesmo tamanho e enquadramento.')
            keyed[key] = key_image(im)
        # recorte à silhueta (união de todas as imagens, com margem): a camada fica bem menor e cada quadro, mais rápido.
        # A borda de baixo é mantida (o corpo continua até o pé da imagem).
        alpha = np.maximum.reduce([np.asarray(i.getchannel('A')) for i in keyed.values()])
        ys, xs = np.where(alpha > 10)
        margin = 24
        x0, x1 = max(0, int(xs.min()) - margin), min(ref_w, int(xs.max()) + 1 + margin)
        y0 = max(0, int(ys.min()) - margin)
        self.crop = (x0, y0, x1, ref_h)
        # `width_px` = largura que a imagem INTEIRA teria; `height_px` = altura da figura recortada (a cabeça nunca sai do quadro)
        self.k = width_px / ref_w if width_px else height_px / (ref_h - y0)
        self.w, self.h = round((x1 - x0) * self.k), round((ref_h - y0) * self.k)
        self.imgs = {key: im.crop(self.crop).resize((self.w, self.h), Image.Resampling.LANCZOS) for key, im in keyed.items()}
        self.base = self.imgs['neutra']
        b = man['boxes']
        self.box = {k: tuple(round(v * self.k) for v in (b[k][0] - x0, b[k][1] - y0, b[k][2] - x0, b[k][3] - y0))
                    for k in ('face', 'mouth', 'eye_l', 'eye_r') if k in b}
        nx, ny = man.get('neck', [ref_w / 2, ref_h * 0.37])
        self.neck = ((nx - x0) * self.k, (ny - y0) * self.k)
        fy0, fy1 = man.get('tilt_fade', [ref_h * 0.34, ref_h * 0.48])
        self.tilt_fade = ((fy0 - y0) * self.k, (fy1 - y0) * self.k)
        self.face_cy = (self.box['face'][1] + self.box['face'][3]) / 2  # centro do rosto (px, a partir do topo da camada)
        self.tilt_gain = float(man.get('tilt_gain', 0.6))
        fw = self.box['face']
        self._face_mask = _feather_mask((fw[2] - fw[0], fw[3] - fw[1]), max(6, round(30 * self.k)))
        mb = self.box['mouth']
        self._mouth_mask = _ellipse_mask((mb[2] - mb[0], mb[3] - mb[1]), max(4, round(12 * self.k)))
        self._eye_mask = {k: _feather_mask((v[2] - v[0], v[3] - v[1]), max(3, round(10 * self.k)))
                          for k, v in self.box.items() if k.startswith('eye')}

    # ---- peças do quadro

    def _expression(self, img, name, weight):
        if name == 'neutra' or name not in self.imgs or weight < 0.02:
            return
        box = self.box['face']
        patch = self.imgs[name].crop(box)
        img.paste(patch, box[:2], _scale_mask(self._face_mask, min(1.0, weight)))

    def _mouth(self, img, openness, width):
        """Boca da vogal falada: abertura gradual (o recorte aberto é achatado) e forma redonda ("o"/"u") ou larga."""
        if openness < 0.05 or not {'falando'} <= set(self.imgs):
            return
        box = self.box['mouth']
        wide = self.imgs['falando'].crop(box)
        round_ = self.imgs.get('surpresa', self.imgs['falando']).crop(box)
        r = _smooth((1.0 - width) / 0.4)  # "o"/"u" (largura ~0,6) = redonda; "a"/"e"/"i" = larga
        patch = Image.blend(wide, round_, r)
        o = min(1.0, openness)
        scale_y = 0.52 + 0.48 * o  # abertura pequena = recorte só um pouco achatado (achatar demais vira borrão escuro)
        h = patch.height
        new_h = max(2, round(h * scale_y))
        squashed = np.asarray(patch.resize((patch.width, new_h), Image.Resampling.LANCZOS))
        top = (h - new_h) // 2  # o que sobra em cima e embaixo repete a pele da borda (nunca buraco transparente nem lábio fechado)
        filled = np.pad(squashed, ((top, h - new_h - top), (0, 0), (0, 0)), mode='edge')
        mask = _scale_mask(self._mouth_mask, _smooth(o / 0.22))  # transição curta: mistura longa deixaria lábios duplicados
        img.paste(Image.fromarray(filled, 'RGBA'), box[:2], mask)

    def _blink(self, img, amount):
        """Piscar: cada olho é achatado em torno do centro e colado sobre a pele (a pálpebra preta vira a linha do olho fechado)."""
        if amount < 0.05:
            return
        for key in ('eye_l', 'eye_r'):
            if key not in self.box:
                continue
            x0, y0, x1, y1 = self.box[key]
            eye = self.base.crop((x0, y0, x1, y1))
            under = np.asarray(self.base.crop((x0 + 6, y1 + 4, x1 - 6, y1 + 14)).convert('RGB')).reshape(-1, 3)
            skin = tuple(int(v) for v in np.median(under, axis=0))
            bg = Image.new('RGBA', eye.size, skin + (255,))
            s = 1.0 - 0.9 * min(1.0, amount)
            new_h = max(2, round(eye.height * s))
            squashed = eye.resize((eye.width, new_h), Image.Resampling.LANCZOS)
            # a linha do olho fechado fica um pouco abaixo do centro (a pálpebra desce)
            cy = (eye.height - new_h) // 2 + round(eye.height * 0.08 * min(1.0, amount))
            bg.paste(squashed, (0, cy), squashed)
            if amount > 0.55:  # olho (quase) fechado: linha de cílios curvada para baixo, como no desenho
                k = min(1.0, (amount - 0.55) / 0.35)
                d = ImageDraw.Draw(bg)
                mid = cy + new_h / 2
                depth = eye.height * 0.10
                pts = [(eye.width * (0.04 + 0.92 * t / 12), mid + depth * math.sin(math.pi * t / 12)) for t in range(13)]
                d.line(pts, fill=(34, 21, 17, int(255 * k)), width=max(2, round(eye.height * 0.075)), joint='curve')
            img.paste(bg, (x0, y0), _scale_mask(self._eye_mask[key], min(1.0, 0.35 + amount)))

    def _warp(self, img, tilt_deg, sway_deg, breath):
        """Inclinação da cabeça + balanço/respiração do corpo numa passada só. O corpo gira em torno do meio da base e
        respira (escala vertical a partir da base); a cabeça ainda gira em torno do pescoço, com peso 1 na cabeça e 0 nos
        ombros. Cada faixa horizontal da imagem de destino vira um quadrilátero da origem; o mapeamento é feito por VÉRTICE
        (vértices compartilhados dão o mesmo ponto), então as faixas não deixam costura."""
        if abs(tilt_deg) < 0.05 and abs(sway_deg) < 0.02 and abs(breath) < 1e-4:
            return img
        w, h = img.size
        top, bottom = self.tilt_fade
        px, py = self.neck
        bx, by = w / 2, h
        t, sy = math.radians(sway_deg), 1.0 + breath
        cb, sb = math.cos(t), math.sin(t)

        def src(x, y):
            u, v = cb * (x - bx) + sb * (y - by), -sb * (x - bx) + cb * (y - by)   # desfaz o giro do corpo
            x1, y1 = bx + u, by + v / sy                                          # e a respiração
            wgt = 1.0 if y1 <= top else 0.0 if y1 >= bottom else _smooth(1 - (y1 - top) / (bottom - top))
            a = math.radians(-tilt_deg * wgt)                                     # e a inclinação da cabeça
            ca, sa = math.cos(a), math.sin(a)
            dx, dy = x1 - px, y1 - py
            return (px + dx * ca - dy * sa, py + dx * sa + dy * ca)
        step = 12
        data = []
        for y in range(0, h, step):
            y1 = min(h, y + step)
            data.append(((0, y, w, y1), (*src(0, y), *src(0, y1), *src(w, y1), *src(w, y))))
        return img.transform(img.size, Image.Transform.MESH, data, Image.Resampling.BILINEAR)

    # ---- quadro

    def render(self, pose: dict) -> Image.Image:
        """Imagem RGBA da personagem (largura `self.w`, altura `self.h`) para a pose do instante."""
        img = self.base.copy()
        expr, weight = pose.get('expr', ('neutral', 0.0))
        self._expression(img, self.map.get(expr, 'neutra'), weight)
        self._mouth(img, pose.get('mouth', 0.0), pose.get('mouth_w', 1.0))
        self._blink(img, pose.get('blink', 0.0))
        return self._warp(img, pose.get('tilt', 0.0) * self.tilt_gain, pose.get('lean', 0.0) * 0.12,
                          0.006 * math.sin(pose.get('breath', 0.0)))
