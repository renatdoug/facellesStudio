"""Renderização de cada cena (movimento de câmera, legenda, fades) e junção das cenas."""
import hashlib
from pathlib import Path

from .util import StudioError, media_duration, run

MIN_CLIP = 0.5  # segundos: trechos menores que isso não servem de fundo

MOTIONS = ('zoom_in', 'zoom_out', 'pan_left', 'pan_right', 'pan_up', 'pan_down', 'shake', 'static')
AUTO_CARD = ('zoom_in', 'zoom_out')  # cartões têm texto na margem: sem pan lateral
AUTO_IMAGE = ('zoom_in', 'pan_right', 'zoom_out', 'pan_left')
AUTO_PORTRAIT = ('zoom_in', 'pan_up', 'zoom_out', 'pan_down')  # no vertical, o deslize lateral rende pouco

# Entradas de cena ("transition"): cut = corte seco; fade = escurece entre cenas; punch = a cena
# "estoura" com um zoom rápido; flash = clarão branco.
ENTRIES = ('cut', 'fade', 'punch', 'flash')
PUNCH_S, PUNCH_ZOOM, FLASH_S = 0.30, 0.12, 0.25


def pick_motion(requested, idx, kind, portrait=False):
    if requested in MOTIONS:
        return requested
    if kind == 'text':  # textos animados ficam parados; o fundo aproxima devagar
        return 'zoom_in'
    seq = AUTO_CARD if kind == 'card' else AUTO_PORTRAIT if portrait else AUTO_IMAGE
    return seq[(idx - 1) % len(seq)]


def motion_exprs(motion, frames, amount, punch_frames=0):
    """Expressões do zoompan. Usam `on` (nº do quadro de saída), então o movimento
    é contínuo do início ao fim da cena. `punch_frames` > 0 soma um zoom rápido (que desacelera)
    nos primeiros quadros."""
    n = max(1, frames - 1)
    cx, cy = '(iw-iw/zoom)/2', '(ih-ih/zoom)/2'
    p = f'+{PUNCH_ZOOM}*pow(max(0,1-on/{punch_frames}),2)' if punch_frames else ''
    if motion == 'zoom_in':
        return f'1+{amount}*on/{n}{p}', cx, cy
    if motion == 'zoom_out':
        return f'1+{amount}-{amount}*on/{n}{p}', cx, cy
    if motion == 'pan_right':
        return f'{1 + amount}{p}', f'(iw-iw/zoom)*on/{n}', cy
    if motion == 'pan_left':
        return f'{1 + amount}{p}', f'(iw-iw/zoom)*(1-on/{n})', cy
    if motion == 'pan_up':
        return f'{1 + amount}{p}', cx, f'(ih-ih/zoom)*(1-on/{n})'
    if motion == 'pan_down':
        return f'{1 + amount}{p}', cx, f'(ih-ih/zoom)*on/{n}'
    if motion == 'shake':  # câmera na mão: tremor pequeno, com folga de zoom para não mostrar borda
        return (f'{1 + max(amount * 0.6, 0.04)}{p}', f'{cx}+sin(on/2.3)*iw*0.006',
                f'{cy}+cos(on/1.7)*ih*0.006')
    if p:
        return f'1{p}', cx, cy
    return '1', '0', '0'


def render_scene(image, ass_name, out, frames, w, h, fps, motion, fade_in, fade_out, fade_s,
                 cwd, amount=0.08, upscale=3, preset='veryfast', crf=20, entry='cut'):
    """Uma imagem -> clipe de vídeo sem áudio, com duração exata de `frames` quadros.
    A imagem é ampliada uma vez (upscale) para o zoom ficar suave, sem tremer."""
    z, x, y = motion_exprs(motion, frames, amount, round(PUNCH_S * fps) if entry == 'punch' else 0)
    seconds = frames / fps
    vf = [f'scale={w * upscale}:{h * upscale}:flags=lanczos',
          f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={fps}",
          'setsar=1',
          f'ass={ass_name}:fontsdir=fonts']
    if fade_in:
        vf.append(f'fade=t=in:st=0:d={fade_s}')
    elif entry == 'flash':
        vf.append(f'fade=t=in:st=0:d={FLASH_S}:color=white')
    if fade_out:
        vf.append(f'fade=t=out:st={max(0, seconds - fade_s):.3f}:d={fade_s}')
    vf.append('format=yuv420p')
    run(['ffmpeg', '-y', '-loglevel', 'error', '-i', image, '-vf', ','.join(vf),
         '-frames:v', frames, '-r', fps, '-c:v', 'libx264', '-preset', preset, '-crf', crf,
         '-pix_fmt', 'yuv420p', '-an', out], cwd=cwd)


def clip_window(src_duration, start=None, end=None):
    """Valida o trecho pedido ("video_start"/"video_end") e devolve (início, duração)."""
    start = float(start or 0)
    if start < 0:
        raise StudioError('"video_start" não pode ser negativo.')
    if start >= src_duration - 0.05:
        raise StudioError(f'"video_start" ({start:g} s) passa do fim do vídeo ({src_duration:.1f} s).')
    stop = src_duration if end in (None, '') else min(float(end), src_duration)
    if stop - start < MIN_CLIP:
        raise StudioError(f'O trecho do vídeo ({start:g} s a {stop:g} s) é curto demais (mínimo {MIN_CLIP} s).')
    return start, stop - start


def prepare_clip(src, dest_dir, idx, w, h, fps, start=None, end=None, preset='veryfast', crf=18):
    """Recorta o trecho, enche o quadro w x h (corte central, sem barras), normaliza o fps e
    descarta o áudio original. O resultado fica em cache: só refaz se algo mudou."""
    src = Path(src)
    st = src.stat()
    start, length = clip_window(media_duration(src), start, end)
    key = hashlib.sha1(f'{src.resolve()}|{st.st_size}|{st.st_mtime_ns}|{start}|{length}|{w}x{h}|{fps}|{crf}'
                       .encode('utf-8')).hexdigest()[:12]
    out = Path(dest_dir) / f'clip_{idx:02}_{key}.mp4'
    if out.exists():
        return out
    vf = (f'scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h},'
          f'fps={fps},setsar=1,format=yuv420p')
    tmp = out.with_name(out.stem + '.part.mp4')
    run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', f'{start:.3f}', '-i', src, '-t', f'{length:.3f}',
         '-an', '-vf', vf, '-c:v', 'libx264', '-preset', preset, '-crf', crf, '-pix_fmt', 'yuv420p', tmp])
    tmp.replace(out)
    return out


def render_video_scene(clip, shade, ass_name, out, frames, w, h, fps, fade_in, fade_out, fade_s,
                       cwd, preset='veryfast', crf=20, entry='cut'):
    """Clipe já preparado (prepare_clip) -> cena com `frames` quadros exatos. Se o trecho for mais
    curto que a narração ele se repete em loop; se for mais longo, é cortado. `clip`, `shade` e
    `ass_name` são nomes relativos a `cwd`."""
    seconds = frames / fps
    if entry == 'punch':  # ampliação rápida no início, que desacelera até o tamanho normal
        k = f'(1+{PUNCH_ZOOM}*pow(max(0,1-t/{PUNCH_S}),2))'
        base = f"[0:v]scale=w='iw*{k}':h='ih*{k}':eval=frame,crop={w}:{h}[b];[b][1:v]overlay=0:0:format=auto"
    else:
        base = '[0:v][1:v]overlay=0:0:format=auto'
    chain = [base, f'ass={ass_name}:fontsdir=fonts', 'setsar=1']
    if fade_in:
        chain.append(f'fade=t=in:st=0:d={fade_s}')
    elif entry == 'flash':
        chain.append(f'fade=t=in:st=0:d={FLASH_S}:color=white')
    if fade_out:
        chain.append(f'fade=t=out:st={max(0, seconds - fade_s):.3f}:d={fade_s}')
    chain.append('format=yuv420p')
    run(['ffmpeg', '-y', '-loglevel', 'error', '-stream_loop', '-1', '-i', clip, '-loop', '1', '-i', shade,
         '-filter_complex', ','.join(chain), '-frames:v', frames, '-r', fps, '-c:v', 'libx264',
         '-preset', preset, '-crf', crf, '-pix_fmt', 'yuv420p', '-an', out], cwd=cwd)


def concat_files(paths, list_file, out):
    """Junta arquivos de mesmo formato sem recodificar."""
    def q(p):
        return str(p).replace('\\', '/').replace("'", "'\\''")
    list_file.write_text(''.join(f"file '{q(p)}'\n" for p in paths), encoding='utf-8')
    run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', list_file,
         '-c', 'copy', out])
