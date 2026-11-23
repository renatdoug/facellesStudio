"""Avaliação automática das imagens de um personagem (saída de tools/personagem_teste.py), SEM chamar nenhuma API.

Mede o que importa para animar por recortes: o quanto o personagem muda entre as expressões (corpo e cabeça), a
qualidade do recorte do fundo magenta e se dá para trocar só o rosto/boca sobre um corpo-base sem emenda visível.
Uso:  python tools/personagem_avaliar.py --dir ../canais/geeklab/personagens/teste_marina
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load(path):
    return Image.open(path).convert('RGB')


def magenta_alpha(im, soft=(60, 150)):
    """Máscara (0..255) do personagem: distância ao magenta do fundo, com transição suave nas bordas (anti-serrilhado)."""
    a = np.asarray(im).astype(np.float32)
    # o fundo é ~ (255, 0, 255) mas com variação (JPEG, leve degradê): usa o fundo REAL medido nos cantos
    corners = np.concatenate([a[:60, :60].reshape(-1, 3), a[:60, -60:].reshape(-1, 3)])
    bg = np.median(corners, axis=0)
    dist = np.sqrt(((a - bg) ** 2).sum(axis=2))
    lo, hi = soft
    alpha = np.clip((dist - lo) / (hi - lo), 0, 1)
    return (alpha * 255).astype(np.uint8), bg


def despill(im, alpha):
    """Tira o "reflexo" magenta das bordas: onde o pixel é semitransparente, R e B acima do verde são reduzidos."""
    a = np.asarray(im).astype(np.float32)
    al = alpha.astype(np.float32) / 255
    edge = (al > 0.02) & (al < 0.98)
    spill = np.minimum(a[..., 0], a[..., 2]) - a[..., 1]
    spill = np.clip(spill, 0, None) * edge * 0.9
    a[..., 0] -= spill
    a[..., 2] -= spill
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def cutout(im):
    alpha, bg = magenta_alpha(im)
    rgba = despill(im, alpha).convert('RGBA')
    rgba.putalpha(Image.fromarray(alpha))
    return rgba, bg


def bbox_of(alpha, thr=128):
    ys, xs = np.where(alpha > thr)
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def phase_shift(a, b):
    """Deslocamento (dx, dy) em pixels que alinha `b` com `a` (correlação de fase em tons de cinza)."""
    A, B = np.fft.fft2(a), np.fft.fft2(b)
    R = A * np.conj(B)
    R /= np.abs(R) + 1e-9
    r = np.fft.ifft2(R).real
    y, x = np.unravel_index(np.argmax(r), r.shape)
    h, w = a.shape
    return (x if x <= w // 2 else x - w), (y if y <= h // 2 else y - h)


def gray_region(im, box, scale=0.5):
    g = im.crop(box).convert('L')
    g = g.resize((int(g.width * scale), int(g.height * scale)), Image.Resampling.LANCZOS)
    arr = np.asarray(g).astype(np.float32)
    arr = (arr - arr.mean()) / (arr.std() + 1e-6)
    win = np.outer(np.hanning(arr.shape[0]), np.hanning(arr.shape[1]))  # janela: evita artefatos de borda
    return arr * win


def region_color(im, alpha, box):
    a = np.asarray(im.crop(box)).astype(np.float32)
    m = np.asarray(Image.fromarray(alpha).crop(box)) > 200
    return [round(float(x), 1) for x in a[m].mean(axis=0)] if m.any() else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', required=True)
    ap.add_argument('--out', help='pasta das imagens de avaliação (padrão: <dir>/avaliacao)')
    args = ap.parse_args()
    d = Path(args.dir)
    out = Path(args.out) if args.out else d / 'avaliacao'
    out.mkdir(parents=True, exist_ok=True)
    files = sorted(d.glob('*_??_*.jpg')) + sorted(d.glob('*_??_*.png'))
    names = [f.stem.split('_', 2)[2] for f in files]
    ims = [load(f) for f in files]
    W, H = ims[0].size
    rep = {'imagens': names, 'tamanho': [W, H], 'recorte': {}, 'consistencia': {}, 'troca_de_rosto': {}}

    # ---- recorte do fundo
    cuts = []
    for n, im in zip(names, ims):
        rgba, bg = cutout(im)
        cuts.append(rgba)
        al = np.asarray(rgba.getchannel('A'))
        x0, y0, x1, y1 = bbox_of(al)
        border = np.concatenate([al[0], al[-1], al[:, 0], al[:, -1]])
        semi = float(((al > 10) & (al < 245)).mean())
        rep['recorte'][n] = {'fundo_medido_rgb': [round(float(v)) for v in bg], 'bbox': [x0, y0, x1, y1],
                             'altura_px': y1 - y0, 'largura_px': x1 - x0,
                             'borda_da_imagem_transparente': bool((border < 10).all()),
                             'fracao_pixels_semitransparentes': round(semi, 4)}
        cuts[-1].save(out / f'recorte_{n}.png')

    # ---- consistência entre as expressões (tudo comparado com a 1ª = base)
    base, base_cut = ims[0], cuts[0]
    head_box = (int(W * 0.15), 0, int(W * 0.85), int(H * 0.42))
    body_box = (0, int(H * 0.45), W, H)
    for n, im, cut in zip(names[1:], ims[1:], cuts[1:]):
        dxh, dyh = phase_shift(gray_region(base, head_box), gray_region(im, head_box))
        dxb, dyb = phase_shift(gray_region(base, body_box), gray_region(im, body_box))
        s = 1 / 0.5  # as regiões foram reduzidas pela metade
        # diferença média de pixels no corpo, depois de alinhar (quanto o corpo "muda" além do deslocamento)
        shifted = ImageChops.offset(im, int(round(dxb * s)), int(round(dyb * s)))
        body_diff = float(np.abs(np.asarray(base.crop(body_box)).astype(np.float32)
                                 - np.asarray(shifted.crop(body_box)).astype(np.float32)).mean())
        rep['consistencia'][n] = {'deslocamento_cabeca_px': [round(dxh * s), round(dyh * s)],
                                  'deslocamento_corpo_px': [round(dxb * s), round(dyb * s)],
                                  'diferenca_media_corpo_0a255': round(body_diff, 2)}
    colors = {}
    for n, im, cut in zip(names, ims, cuts):
        al = np.asarray(cut.getchannel('A'))
        colors[n] = {'cabelo': region_color(im, al, (int(W * 0.28), int(H * 0.03), int(W * 0.40), int(H * 0.10))),
                     'cardigan': region_color(im, al, (int(W * 0.12), int(H * 0.42), int(W * 0.22), int(H * 0.50))),
                     'calca': region_color(im, al, (int(W * 0.34), int(H * 0.82), int(W * 0.46), int(H * 0.90))),
                     'pele_rosto': region_color(im, al, (int(W * 0.42), int(H * 0.10), int(W * 0.52), int(H * 0.13)))}
    rep['consistencia']['cores_medias_rgb'] = colors

    # ---- troca só do rosto sobre o corpo-base (como a animação por recortes faria)
    face = (int(W * 0.30), int(H * 0.12), int(W * 0.70), int(H * 0.36))   # testa até o queixo, dentro do cabelo
    mouth = (int(W * 0.40), int(H * 0.24), int(W * 0.60), int(H * 0.31))  # só a região da boca
    sheet = [base_cut]
    for tag, box, feather in (('rosto', face, 30), ('boca', mouth, 14)):
        for n, im in zip(names[1:], ims[1:]):
            # alinha a expressão à base pela cabeça antes de recortar o pedaço (compensa o deslocamento medido)
            dx, dy = rep['consistencia'][n]['deslocamento_cabeca_px']
            aligned = ImageChops.offset(im, dx, dy)
            patch = aligned.crop(box)
            mask = Image.new('L', patch.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle((feather, feather, patch.width - feather, patch.height - feather), radius=feather, fill=255)
            mask = mask.filter(ImageFilter.GaussianBlur(feather / 2))
            comp = base.copy()
            comp.paste(patch, (box[0], box[1]), mask)
            comp.save(out / f'troca_{tag}_{n}.jpg', quality=92)
            diff = np.abs(np.asarray(comp.crop(box)).astype(np.float32) - np.asarray(base.crop(box)).astype(np.float32)).mean()
            rep['troca_de_rosto'][f'{tag}_{n}'] = {'caixa': list(box), 'diferenca_media_vs_base': round(float(diff), 2)}

    # ---- folhas para olhar
    tw, th = 420, 560
    # recortes sobre fundo contrastante (mostra halo magenta, se houver)
    bgs = [(70, 130, 150), (235, 235, 225)]
    sheet1 = Image.new('RGB', (tw * len(ims) + 10 * (len(ims) - 1), th * 2 + 10), (255, 255, 255))
    for row, color in enumerate(bgs):
        for i, c in enumerate(cuts):
            comp = Image.new('RGB', c.size, color)
            comp.paste(c, (0, 0), c)
            sheet1.paste(comp.resize((tw, th), Image.Resampling.LANCZOS), (i * (tw + 10), row * (th + 10)))
    sheet1.save(out / 'folha_recortes.png')
    # zoom nas bordas do cabelo (onde o recorte costuma falhar)
    zbox = (int(W * 0.25), int(H * 0.04), int(W * 0.45), int(H * 0.14))
    zoom = Image.new('RGB', (480 * 2, 240 * 2 + 10), (255, 255, 255))
    for i, c in enumerate(cuts[:2]):
        for row, color in enumerate(bgs):
            comp = Image.new('RGB', c.size, color)
            comp.paste(c, (0, 0), c)
            zoom.paste(comp.crop(zbox).resize((480, 240), Image.Resampling.LANCZOS), (i * 480, row * 250))
    zoom.save(out / 'zoom_borda_cabelo.png')
    # trocas
    cols = len(names) - 1
    sheet2 = Image.new('RGB', (tw * (cols + 1) + 10 * cols, th * 2 + 10), (255, 255, 255))
    sheet2.paste(base.resize((tw, th), Image.Resampling.LANCZOS), (0, 0))
    for row, tag in enumerate(('rosto', 'boca')):
        for i, n in enumerate(names[1:]):
            im = Image.open(out / f'troca_{tag}_{n}.jpg')
            sheet2.paste(im.resize((tw, th), Image.Resampling.LANCZOS), ((i + 1) * (tw + 10), row * (th + 10)))
    sheet2.save(out / 'folha_trocas.png')
    # rostos grandes das trocas (para ver a emenda)
    fw, fh = 440, 470
    seam = Image.new('RGB', (fw * (cols + 1) + 10 * cols, fh * 2 + 10), (255, 255, 255))
    crop = (int(W * 0.22), int(H * 0.03), int(W * 0.78), int(H * 0.35))
    seam.paste(base.crop(crop).resize((fw, fh), Image.Resampling.LANCZOS), (0, 0))
    for row, tag in enumerate(('rosto', 'boca')):
        for i, n in enumerate(names[1:]):
            im = Image.open(out / f'troca_{tag}_{n}.jpg')
            seam.paste(im.crop(crop).resize((fw, fh), Image.Resampling.LANCZOS), ((i + 1) * (fw + 10), row * (fh + 10)))
    seam.save(out / 'folha_emendas.png')

    (out / 'avaliacao.json').write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(rep, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
