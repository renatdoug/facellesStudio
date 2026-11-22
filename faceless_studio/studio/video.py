"""Renderização de cada cena (movimento de câmera, legenda, fades) e junção das cenas."""
from .util import run

MOTIONS = ('zoom_in', 'zoom_out', 'pan_left', 'pan_right', 'static')
AUTO_CARD = ('zoom_in', 'zoom_out')  # cartões têm texto na margem: sem pan lateral
AUTO_IMAGE = ('zoom_in', 'pan_right', 'zoom_out', 'pan_left')


def pick_motion(requested, idx, kind):
    if requested in MOTIONS:
        return requested
    if kind == 'text':  # textos animados ficam parados; o fundo aproxima devagar
        return 'zoom_in'
    seq = AUTO_CARD if kind == 'card' else AUTO_IMAGE
    return seq[(idx - 1) % len(seq)]


def motion_exprs(motion, frames, amount):
    """Expressões do zoompan. Usam `on` (nº do quadro de saída), então o movimento
    é contínuo do início ao fim da cena."""
    n = max(1, frames - 1)
    cx, cy = '(iw-iw/zoom)/2', '(ih-ih/zoom)/2'
    if motion == 'zoom_in':
        return f'1+{amount}*on/{n}', cx, cy
    if motion == 'zoom_out':
        return f'1+{amount}-{amount}*on/{n}', cx, cy
    if motion == 'pan_right':
        return f'{1 + amount}', f'(iw-iw/zoom)*on/{n}', cy
    if motion == 'pan_left':
        return f'{1 + amount}', f'(iw-iw/zoom)*(1-on/{n})', cy
    return '1', '0', '0'


def render_scene(image, ass_name, out, frames, w, h, fps, motion, fade_in, fade_out, fade_s,
                 cwd, amount=0.08, upscale=3, preset='veryfast', crf=20):
    """Uma imagem -> clipe de vídeo sem áudio, com duração exata de `frames` quadros.
    A imagem é ampliada uma vez (upscale) para o zoom ficar suave, sem tremer."""
    z, x, y = motion_exprs(motion, frames, amount)
    seconds = frames / fps
    vf = [f'scale={w * upscale}:{h * upscale}:flags=lanczos',
          f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={fps}",
          'setsar=1',
          f'ass={ass_name}:fontsdir=fonts']
    if fade_in:
        vf.append(f'fade=t=in:st=0:d={fade_s}')
    if fade_out:
        vf.append(f'fade=t=out:st={max(0, seconds - fade_s):.3f}:d={fade_s}')
    vf.append('format=yuv420p')
    run(['ffmpeg', '-y', '-loglevel', 'error', '-i', image, '-vf', ','.join(vf),
         '-frames:v', frames, '-r', fps, '-c:v', 'libx264', '-preset', preset, '-crf', crf,
         '-pix_fmt', 'yuv420p', '-an', out], cwd=cwd)


def concat_files(paths, list_file, out):
    """Junta arquivos de mesmo formato sem recodificar."""
    def q(p):
        return str(p).replace('\\', '/').replace("'", "'\\''")
    list_file.write_text(''.join(f"file '{q(p)}'\n" for p in paths), encoding='utf-8')
    run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', list_file,
         '-c', 'copy', out])
