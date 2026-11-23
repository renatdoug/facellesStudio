"""Experimento: UM personagem em 4 expressões pelo Gemini (consistência visual para personagens "de recortes").

Gasta dinheiro de verdade (4 imagens, ~R$ 0,62 cada em 2K, medido pelo Renato). Por isso:
  - sem `--gerar` ele só MOSTRA o que faria e o custo estimado (nada é chamado);
  - gera no máximo 4 imagens, uma vez cada; imagem que já existe é pulada (nunca sobrescreve, não cobra de novo);
  - a 1ª imagem vem só do texto; as outras 3 usam a 1ª como IMAGEM DE REFERÊNCIA (edição por imagem), para manter o rosto;
  - fundo magenta sólido (#FF00FF): nenhuma peça do personagem usa magenta, então dá para recortar por código.
Uso:  python tools/personagem_teste.py --dir ../canais/geeklab/personagens/teste_marina [--gerar]
"""
import argparse
import io
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from studio import images_ai  # noqa: E402

PRICE_BRL = 0.62  # por imagem 2K (medido em 22/11/2026, igual em 16:9 e 9:16)
CHROMA = '#FF00FF'

CHARACTER = (
    'A single original adult female character for an animated Brazilian telenovela, 2D cartoon style, clean bold dark '
    'outlines, flat colors with subtle cel shading, expressive large eyes. She has medium-tan skin, shoulder-length wavy '
    'dark-brown hair with a side part, warm brown eyes, a mustard-yellow cardigan over a white blouse, and dark navy '
    'trousers. No accessories. Three-quarter length view from the top of the head to mid-thigh, perfectly front-facing '
    'and centered, arms relaxed at her sides, shoulders level, the same camera distance and framing every time. '
    f'Plain solid flat pure magenta background ({CHROMA}), no floor, no shadow, no gradient, no scenery, nothing else '
    'in the image. No text, no letters, no watermark, no logo.')

EXPRESSIONS = [
    ('neutra', 'Expression: neutral and calm, mouth gently CLOSED, eyes open and looking straight at the viewer, eyebrows relaxed.'),
    ('feliz', 'Expression: happy, a warm broad smile with the mouth closed or only slightly open, cheeks lifted, eyes bright, eyebrows relaxed and slightly raised.'),
    ('surpresa', 'Expression: surprised, eyebrows raised high, eyes wide open, mouth open in a small round "o" shape.'),
    ('falando', 'Expression: speaking mid-sentence, mouth moderately OPEN as if saying "ah" with the upper teeth and a bit of tongue visible, eyes open and looking at the viewer, eyebrows relaxed.'),
]

KEEP = ('This is the same character as the reference image. Redraw EXACTLY this character: identical face shape, eyes, nose, '
        'hair, skin tone, outfit, colors, body proportions, line style, pose, camera distance, framing and position in the '
        'image, and the same flat magenta background. Change ONLY the facial expression. ')


def prompts(name):
    out = []
    for i, (key, text) in enumerate(EXPRESSIONS):
        out.append((f'{name}_{i + 1:02}_{key}', f'{CHARACTER} {text}' if i == 0 else f'{KEEP}{text} No text, no watermark.'))
    return out


def save_image(raw, base: Path):
    im = Image.open(io.BytesIO(raw))
    ext = {'PNG': '.png', 'JPEG': '.jpg', 'WEBP': '.webp'}.get(im.format, '.png')
    path = base.with_suffix(ext)
    if path.exists():  # nunca sobrescreve
        raise FileExistsError(path)
    with open(path, 'xb') as f:
        f.write(raw)
    alpha = im.mode in ('RGBA', 'LA') or 'transparency' in im.info
    transparent = bool(alpha and im.convert('RGBA').getchannel('A').getextrema()[0] < 250)
    return path, {'format': im.format, 'mode': im.mode, 'size': list(im.size), 'bytes': len(raw), 'has_real_transparency': transparent}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--dir', required=True, help='pasta de saída (criada se não existir)')
    ap.add_argument('--name', default='marina')
    ap.add_argument('--env', help='arquivo .env com GEMINI_API_KEY')
    ap.add_argument('--gerar', action='store_true', help='chama o Gemini de verdade (gasta ~R$ 0,62 por imagem)')
    ap.add_argument('--aspect', default='3:4')
    args = ap.parse_args()

    out = Path(args.dir)
    items = prompts(args.name)
    existing = [k for k, _ in items if any(out.glob(f'{k}.*'))]
    todo = [(k, p) for k, p in items if k not in existing]
    print(f'Personagem "{args.name}": {len(items)} imagens previstas, {len(existing)} já existem (puladas), {len(todo)} a gerar.')
    print(f'Custo estimado: {len(todo)} x R$ {PRICE_BRL:.2f} = R$ {len(todo) * PRICE_BRL:.2f} (2K, preço medido; confira o saldo no AI Studio).')
    if not args.gerar:
        for k, p in todo:
            print(f'\n--- {k} ---\n{p}')
        print('\n(simulação: nada foi chamado. Use --gerar para gerar.)')
        return
    if not todo:
        return
    if args.env:
        images_ai.load_dotenv(args.env)
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / 'manifesto.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}

    cfg = dict(images_ai.DEFAULTS['gemini'], aspect=args.aspect, prompt_suffix='')
    reference = None
    first = next(iter(out.glob(f'{items[0][0]}.*')), None)
    if first:
        reference = (f'image/{"jpeg" if first.suffix == ".jpg" else first.suffix[1:]}', first.read_bytes())
    for key, prompt in todo:
        if key != items[0][0] and reference is None:
            print('Sem a imagem de referência (a 1ª): interrompido para não gastar à toa.')
            break
        t0 = time.time()
        c = dict(cfg)
        if key != items[0][0]:
            c['references'] = [reference]
        print(f'Gerando {key} ({"com referência" if c.get("references") else "só texto"})...', flush=True)
        try:
            raw = images_ai.gen_gemini(prompt, c, 1)
        except images_ai.ImageGenError as err:
            print(f'  FALHOU (não tentei de novo, para não gastar): {err}')
            manifest[key] = {'erro': str(err)[:400], 'prompt': prompt}
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
            break
        path, info = save_image(raw, out / key)
        info.update(prompt=prompt, seconds=round(time.time() - t0, 1), model=cfg['model'], image_size=cfg['image_size'],
                    aspect=cfg['aspect'], used_reference=bool(c.get('references')), file=path.name)
        manifest[key] = info
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'  ok: {path.name} {info["size"]} {info["format"]}/{info["mode"]} em {info["seconds"]} s; transparência real: {info["has_real_transparency"]}')
        if key == items[0][0]:
            reference = (f'image/{"jpeg" if path.suffix == ".jpg" else path.suffix[1:]}', raw)
    done = sum(1 for v in manifest.values() if 'erro' not in v)
    print(f'\nImagens geradas no total: {done}. Custo estimado acumulado: R$ {done * PRICE_BRL:.2f}.')


if __name__ == '__main__':
    main()
