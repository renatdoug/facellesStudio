"""Fundos e artes das cenas (Pillow): fundo da marca, cartão de título e tratamento de imagens."""
import math
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .util import StudioError

PALETTES = {
    'health': {'dark': (8, 26, 48), 'mid': (11, 93, 106), 'accent': (103, 233, 208),
               'muted': (120, 150, 170), 'alert': (255, 138, 128)},
    'geek': {'dark': (27, 13, 47), 'mid': (87, 38, 129), 'accent': (243, 183, 74),
             'muted': (160, 140, 190), 'alert': (255, 110, 150)},
}

BOLD_FONTS = [
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
    '/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf',
    'C:/Windows/Fonts/arialbd.ttf',
    '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
    '/Library/Fonts/Arial Bold.ttf',
]
REGULAR_FONTS = [
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
    '/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf',
    'C:/Windows/Fonts/arial.ttf',
    '/System/Library/Fonts/Supplemental/Arial.ttf',
    '/Library/Fonts/Arial.ttf',
]


def palette(theme):
    return PALETTES.get(theme, PALETTES['health'])


def find_font(bold=True, override=None):
    """Caminho da fonte. `override` (do roteiro) tem prioridade."""
    if override:
        p = Path(override)
        if not p.exists():
            raise StudioError(f'Fonte não encontrada: {p}')
        return p
    for c in (BOLD_FONTS if bold else REGULAR_FONTS):
        if Path(c).exists():
            return Path(c)
    raise StudioError('Nenhuma fonte encontrada. Informe "font_bold" e "font_regular" no roteiro.')


def font_family(path):
    """Nome da família da fonte, usado pelas legendas ASS."""
    return ImageFont.truetype(str(path), 20).getname()[0]


def wrap_lines(text, font_path, size, max_w):
    """Quebra o texto em linhas que cabem em `max_w` pixels (medindo com a fonte real)."""
    f = ImageFont.truetype(str(font_path), size)
    lines = []
    for para in str(text).split('\n'):
        cur = ''
        for word in para.split():
            test = f'{cur} {word}'.strip()
            if cur and f.getlength(test) > max_w:
                lines.append(cur)
                cur = word
            else:
                cur = test
        lines.append(cur)
    return [ln for ln in lines if ln] or ['']


def text_width(text, font_path, size):
    return ImageFont.truetype(str(font_path), size).getlength(str(text))


def _gradient(w, h, dark, mid):
    sw, sh = 64, 36  # gera pequeno e amplia: rápido mesmo em 4K
    small = Image.new('RGB', (sw, sh))
    px = small.load()
    for y in range(sh):
        for x in range(sw):
            f = min(1.0, 0.35 * y / (sh - 1) + 0.45 * x / (sw - 1))
            px[x, y] = tuple(round(a * (1 - f) + b * f) for a, b in zip(dark, mid))
    return small.resize((w, h), Image.Resampling.BICUBIC)


def base_background(w, h, theme, channel, idx, fonts, waves=True):
    """Fundo da identidade visual: degradê, grade, ondas e nome do canal."""
    pal = palette(theme)
    accent = pal['accent']
    im = _gradient(w, h, pal['dark'], pal['mid'])
    draw = ImageDraw.Draw(im, 'RGBA')
    step = max(40, w // 24)
    for x in range(0, w, step):
        draw.line((x, 0, x, h), fill=(255, 255, 255, 9), width=1)
    for y in range(0, h, step):
        draw.line((0, y, w, y), fill=(255, 255, 255, 9), width=1)
    if waves:
        for j in range(3):
            pts = [(x, int(h * (0.67 + 0.03 * j) + math.sin(x / (w * 0.05) + j * 1.3 + idx) * h * 0.022))
                   for x in range(0, w + 1, 8)]
            draw.line(pts, fill=(*accent, 70 - j * 20), width=max(2, h // 360))
    pad = int(w * 0.075)
    label = ImageFont.truetype(str(fonts['regular']), max(16, int(h * 0.030)))
    draw.text((pad, int(h * 0.10)), channel.upper(), font=label, fill=(*accent, 255))
    return im


def _fit_headline(draw, text, max_w, start_size, bold_path, max_lines=3):
    size = start_size
    while size > 24:
        lines = wrap_lines(text, bold_path, size, max_w)
        if len(lines) <= max_lines:
            return ImageFont.truetype(str(bold_path), size), lines, size
        size -= 2
    return ImageFont.truetype(str(bold_path), size), wrap_lines(text, bold_path, size, max_w)[:max_lines], size


def make_card(scene, idx, dest, w, h, channel, theme, fonts):
    """Cartão de título. Reserva a faixa inferior para a legenda e mantém margens
    que sobrevivem ao zoom."""
    accent = palette(theme)['accent']
    im = base_background(w, h, theme, channel, idx, fonts)
    draw = ImageDraw.Draw(im, 'RGBA')
    pad = int(w * 0.075)
    headline = scene.get('headline') or scene.get('title') or f'CENA {idx}'
    hfont, lines, size = _fit_headline(draw, headline, w - 2 * pad, int(h * 0.085), fonts['bold'])
    y = int(h * 0.24)
    for ln in lines:
        draw.text((pad, y), ln, font=hfont, fill=(255, 255, 255, 255))
        y += int(size * 1.2)
    y += int(h * 0.03)
    bar_h = max(4, int(h * 0.008))
    draw.rounded_rectangle((pad, y, pad + int(w * 0.09), y + bar_h), radius=bar_h // 2, fill=(*accent, 255))
    y += int(h * 0.04)
    visual = scene.get('visual', '')
    if visual:
        size = max(16, int(h * 0.034))
        sub = ImageFont.truetype(str(fonts['regular']), size)
        for ln in wrap_lines(visual, fonts['regular'], size, w - 2 * pad)[:2]:
            if y > h * 0.76:
                break
            draw.text((pad, y), ln, font=sub, fill=(212, 238, 244, 255))
            y += int(size * 1.35)
    im.save(dest)


def fit_16x9(source, w, h):
    """Abre uma imagem e recorta no centro para w x h (sem barras pretas)."""
    im = Image.open(source).convert('RGB')
    factor = max(w / im.width, h / im.height)
    nw, nh = math.ceil(im.width * factor), math.ceil(im.height * factor)
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    x, y = (nw - w) // 2, (nh - h) // 2
    return im.crop((x, y, x + w, y + h))


def _shade_mask(w, h, darken_top=False):
    """Escurecimento da base (e opcionalmente do topo) para legenda e título ficarem legíveis.
    No vertical a legenda fica em ~75% da altura (acima da faixa do Shorts), então o degradê começa mais
    cedo e já está forte nessa altura; no horizontal ela fica na base e o degradê é o de sempre."""
    portrait = h > w
    shade = Image.new('L', (1, 256))
    for y in range(256):
        t = y / 255
        if portrait:
            x = min(1.0, max(0.0, (t - 0.50) / 0.28))
            bottom = 0.70 * x * x * (3 - 2 * x)
        else:
            bottom = max(0.0, (t - 0.62) / 0.38) ** 1.4 * 0.70
        top = max(0.0, (0.30 - t) / 0.30) ** 1.4 * 0.55 if darken_top else 0.0
        shade.putpixel((0, y), int(255 * max(bottom, top)))
    return shade.resize((w, h), Image.Resampling.BICUBIC)


def finish_photo(im, darken_top=False):
    """Escurece a base (e opcionalmente o topo) para a legenda e o título ficarem legíveis."""
    w, h = im.size
    black = Image.new('RGB', (w, h), (0, 0, 0))
    return Image.composite(black, im, _shade_mask(w, h, darken_top))


def shade_overlay(w, h, darken_top=False):
    """Mesmo escurecimento de finish_photo, como camada RGBA para sobrepor a um vídeo."""
    layer = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    layer.putalpha(_shade_mask(w, h, darken_top))
    return layer


def contact_sheet(items, dest, thumb_w=480, cols=3, font_path=None):
    """Folha de revisão: miniaturas numeradas de todas as cenas."""
    if not items:
        return
    thumb_h = thumb_w * 9 // 16
    cap = 46
    rows = math.ceil(len(items) / cols)
    sheet = Image.new('RGB', (cols * thumb_w + (cols + 1) * 12, rows * (thumb_h + cap) + (rows + 1) * 12),
                      (20, 22, 28))
    draw = ImageDraw.Draw(sheet)
    f = ImageFont.truetype(str(font_path), 15) if font_path else ImageFont.load_default()
    for n, (label, path) in enumerate(items):
        r, c = divmod(n, cols)
        x, y = 12 + c * (thumb_w + 12), 12 + r * (thumb_h + cap + 12)
        try:
            th = Image.open(path).convert('RGB').resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
            sheet.paste(th, (x, y))
        except OSError:
            draw.rectangle((x, y, x + thumb_w, y + thumb_h), outline=(200, 60, 60))
        for k, ln in enumerate(textwrap.wrap(label, 58)[:2]):
            draw.text((x, y + thumb_h + 4 + k * 19), ln, font=f, fill=(225, 230, 235))
    sheet.save(dest, quality=90)
