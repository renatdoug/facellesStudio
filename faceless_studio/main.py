#!/usr/bin/env python3
"""Faceless Studio — roteiro JSON -> vídeo MP4 narrado, legendado, com cenas que mudam
de formato conforme o conteúdo e imagens geradas por IA.

Uso rápido:
    python main.py --images-only         # gera só as imagens e a folha de revisão
    python main.py                       # vídeo completo
    python main.py --preview             # 2 primeiras cenas, 720p
    python main.py --preview --no-voice  # teste offline, áudio mudo
"""
import argparse
import json
import math
import re
import shutil
import sys
import time
from pathlib import Path

from studio import __version__, audio, images_ai, layouts, subtitles, video, visuals, voice
from studio.util import StudioError, check_ffmpeg, ensure_dir

ROOT = Path(__file__).resolve().parent
FADE = 0.4
TAIL = 0.35


def parse_args():
    p = argparse.ArgumentParser(description='Gera vídeo faceless narrado a partir de um roteiro JSON')
    p.add_argument('--script', default='roteiro_uti.json', help='Roteiro JSON')
    p.add_argument('--output', default='output/video_final.mp4')
    p.add_argument('--voice', help='Ex.: pt-BR-FranciscaNeural')
    p.add_argument('--rate', help='Velocidade da voz, ex.: +8%%')
    p.add_argument('--res', help='Resolução, ex.: 1920x1080')
    p.add_argument('--music', help='Trilha (substitui a do roteiro). "none" desliga.')
    p.add_argument('--subtitles', choices=list(subtitles.CAPTION_MODES))
    p.add_argument('--preview', action='store_true', help='Só as 2 primeiras cenas, em rascunho (720p)')
    p.add_argument('--draft', action='store_true',
                   help='Rascunho: 720p mantendo o formato do vídeo (horizontal, vertical ou quadrado)')
    p.add_argument('--scenes', help='Intervalo de cenas, ex.: 3-5')
    p.add_argument('--no-voice', action='store_true', help='Teste offline: áudio mudo (não publicar)')
    p.add_argument('--force-voice', action='store_true', help='Gera a narração de novo')
    p.add_argument('--image-provider', help='pollinations, openai, gemini, comfyui ou none')
    p.add_argument('--images-only', action='store_true', help='Gera as imagens e a folha de revisão, e para')
    p.add_argument('--regen', help='Gera de novo as imagens destas cenas, ex.: 2,5')
    p.add_argument('--strict-images', action='store_true', help='Interrompe se uma imagem falhar '
                                                                '(padrão: usa cartão no lugar e avisa)')
    p.add_argument('--preset', default='veryfast', help='Preset do x264')
    p.add_argument('--version', action='version', version=f'Faceless Studio {__version__}')
    return p.parse_args()


def load_script(path):
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        raise StudioError(f'Roteiro não encontrado: {path}')
    except json.JSONDecodeError as e:
        raise StudioError(f'Roteiro com JSON inválido (linha {e.lineno}, coluna {e.colno}): {e.msg}')
    return validate_script(data)


def validate_script(data):
    """Valida o conteúdo de um roteiro já carregado (usado também pela interface web)."""
    if not isinstance(data, dict):
        raise StudioError('O roteiro precisa ser um objeto JSON.')
    if data.get('default_transition', 'cut') not in video.ENTRIES:
        raise StudioError('"default_transition" deve ser ' + ', '.join(video.ENTRIES) + '.')
    if data.get('subtitles', 'karaoke') not in subtitles.CAPTION_MODES:
        raise StudioError('"subtitles" deve ser ' + ', '.join(subtitles.CAPTION_MODES) + '.')
    if 'resolution' in data and not re.fullmatch(r'\d{3,5}x\d{3,5}', str(data['resolution']).lower()):
        raise StudioError('"resolution" deve ter o formato LARGURAxALTURA, ex.: 1920x1080 ou 1080x1920.')
    scenes = data.get('scenes')
    if not isinstance(scenes, list) or not scenes:
        raise StudioError('O roteiro precisa ter uma lista "scenes" com pelo menos uma cena.')
    for n, s in enumerate(scenes, 1):
        if not isinstance(s, dict):
            raise StudioError(f'A cena {n} precisa ser um objeto.')
        if not str(s.get('narration', '')).strip():
            raise StudioError(f'A cena {n} está sem "narration".')
        if s.get('transition', 'cut') not in video.ENTRIES:
            raise StudioError(f'Cena {n}: "transition" deve ser ' + ', '.join(video.ENTRIES) + '.')
        if s.get('motion', 'auto') not in ('auto',) + video.MOTIONS:
            raise StudioError(f'Cena {n}: "motion" deve ser auto, ' + ', '.join(video.MOTIONS) + '.')
        layouts.detect_layout(s)  # valida "layout"
        for key in ('video_start', 'video_end'):
            if s.get(key) not in (None, '') and (isinstance(s[key], bool) or not isinstance(s[key], (int, float))
                                                 or s[key] < 0):
                raise StudioError(f'Cena {n}: "{key}" deve ser um número de segundos (0 ou mais).')
        if s.get('video_end') not in (None, '') and s['video_end'] <= (s.get('video_start') or 0):
            raise StudioError(f'Cena {n}: "video_end" precisa ser maior que "video_start".')
        if s.get('video') is not None and not isinstance(s['video'], str):
            raise StudioError(f'Cena {n}: "video" deve ser o caminho de um arquivo de vídeo.')
    return data


def draft_resolution(resolution):
    """720p do mesmo formato: 1920x1080 -> 1280x720, 1080x1920 -> 720x1280, 1080x1080 -> 720x720."""
    w, h = map(int, str(resolution).lower().split('x'))
    k = 720 / min(w, h)
    return f'{round(w * k / 2) * 2}x{round(h * k / 2) * 2}'


def select_scenes(scenes, args):
    if args.preview:
        return list(enumerate(scenes[:2], 1))
    if args.scenes:
        a, _, b = args.scenes.partition('-')
        a, b = int(a), int(b or a)
        return [(i, s) for i, s in enumerate(scenes, 1) if a <= i <= b]
    return list(enumerate(scenes, 1))


def fmt_clock(t):
    t = int(t)
    return f'{t // 3600}:{(t // 60) % 60:02}:{t % 60:02}' if t >= 3600 else f'{t // 60}:{t % 60:02}'


def write_chapters(path, starts, total):
    """Capítulos do YouTube: 1º em 0:00, pelo menos 3, cada um com 10 s ou mais."""
    if not starts:
        return None
    starts = ([(0.0, 'Introdução')] + starts) if starts[0][0] > 0 else [(0.0, starts[0][1])] + starts[1:]
    bounds = [t for t, _ in starts] + [total]
    short = [name for (t, name), nxt in zip(starts, bounds[1:]) if nxt - t < 10]
    path.write_text('\n'.join(f'{fmt_clock(t)} {name}' for t, name in starts) + '\n', encoding='utf-8')
    warn = []
    if len(starts) < 3:
        warn.append('o YouTube exige pelo menos 3 capítulos')
    if short:
        warn.append('capítulos com menos de 10 s: ' + ', '.join(short))
    return warn


def entry_of(scene, data):
    """Entrada da cena: o "transition" dela ou o "default_transition" do roteiro."""
    return scene.get('transition') or data.get('default_transition') or 'cut'


def scene_id(idx, scene):
    return str(scene.get('id') or f'{idx:02}')


def resolve_images(chosen, data, script_dir, args, w, h, fonts, out_dir):
    """Fase 1: garante a imagem de cada cena que usa foto/ilustração (arquivo próprio ou IA)."""
    settings = dict(data.get('images') or {})
    if args.image_provider:
        settings['provider'] = args.image_provider
    bank = images_ai.ImageBank(script_dir, settings, install_dir=ROOT,
                               orientation=images_ai.orientation_of(w, h))
    regen = {int(x) for x in args.regen.split(',')} if args.regen else set()
    resolved, review, warnings = {}, [], []
    todo = [(i, s) for i, s in chosen if layouts.detect_layout(s) == 'image']
    to_generate = [i for i, s in todo if not s.get('image') and s.get('prompt')]
    if to_generate:
        print(f'Imagens por IA: {len(to_generate)} cena(s), fornecedor "{bank.provider}"', flush=True)
    for idx, scene in todo:
        if scene.get('image'):
            src = (script_dir / scene['image']).resolve()
            if not src.exists():
                raise StudioError(f'Imagem da cena {idx} não encontrada: {src}')
            resolved[idx] = src
        else:
            try:
                t0 = time.time()
                src, new = bank.get(scene_id(idx, scene), scene['prompt'], regen=idx in regen)
                print(f'  cena {idx}: {"gerada" if new else "do cache"} ({time.time() - t0:.0f} s) -> {src.name}',
                      flush=True)
                resolved[idx] = src
            except images_ai.ImageGenError as e:
                if args.strict_images:
                    raise StudioError(f'Cena {idx}: falha ao gerar imagem: {e}')
                msg = f'cena {idx}: imagem não gerada ({e}). Usando cartão no lugar.'
                print('  Atenção: ' + msg, flush=True)
                warnings.append(msg)
                continue
        label = f'{idx:02} · ' + (scene.get('prompt') or scene.get('image'))
        review.append((label, resolved[idx]))
    if review:
        sheet = out_dir / 'revisao_imagens.jpg'
        visuals.contact_sheet(review, sheet, font_path=fonts['regular'])
        print(f'Folha de revisão das imagens: {sheet}', flush=True)
    return resolved, warnings


def resolve_videos(chosen, script_dir):
    """Confere, antes de renderizar qualquer coisa, que o vídeo de cada cena existe."""
    found = {}
    for idx, scene in chosen:
        if layouts.detect_layout(scene) != 'video':
            continue
        if not scene.get('video'):
            raise StudioError(f'Cena {idx}: o tipo é "vídeo", mas nenhum arquivo foi escolhido (campo "video").')
        src = Path(scene['video'])
        src = src if src.is_absolute() else (script_dir / src)
        if not src.is_file():
            raise StudioError(f'Vídeo da cena {idx} não encontrado: {src.resolve()}')
        found[idx] = src.resolve()
    return found


def main():
    args = parse_args()
    t0 = time.time()
    check_ffmpeg()
    script = (ROOT / args.script).resolve()
    data = load_script(script)
    # Tudo o que este roteiro gera (imagens, cache, saída) fica junto dele, não na pasta
    # de instalação — assim vários canais/roteiros não disputam os mesmos arquivos.
    project_dir = script.parent
    # Chaves: o .env do próprio canal tem prioridade; o da instalação serve de padrão
    # compartilhado para quem não define um por projeto.
    images_ai.load_dotenv(project_dir / '.env')
    images_ai.load_dotenv(ROOT / '.env')

    full_res = data.get('resolution', '1920x1080')
    res = args.res or (draft_resolution(full_res) if (args.preview or args.draft) else full_res)
    w, h = map(int, res.lower().split('x'))
    if w % 2 or h % 2:
        raise StudioError('A resolução precisa ter largura e altura pares.')
    fps = int(data.get('fps', 30))
    theme = data.get('theme', 'health')
    channel = data.get('channel', 'CANAL')
    voice_name = args.voice or data.get('voice', 'pt-BR-AntonioNeural')
    rate = args.rate or data.get('rate', '+0%')
    sub_mode = args.subtitles or data.get('subtitles', 'karaoke')
    accent = visuals.palette(theme)['accent']
    motion_amount = float(data.get('motion_amount', 0.08))

    music = args.music if args.music is not None else data.get('music')
    if music and music.lower() != 'none':
        music = Path(music) if Path(music).is_absolute() else (script.parent / music).resolve()
        if not music.exists():
            raise StudioError(f'Trilha não encontrada: {music}')
    else:
        music = None

    work = ensure_dir(project_dir / 'temp')
    cache = ensure_dir(work / 'cache')
    fonts_dir = ensure_dir(work / 'fonts')
    fonts = {'bold': visuals.find_font(True, data.get('font_bold')),
             'regular': visuals.find_font(False, data.get('font_regular'))}
    for f in fonts.values():
        shutil.copy2(f, fonts_dir / f.name)
    font_name = visuals.font_family(fonts['bold'])
    out_arg = Path(args.output)
    output = out_arg if out_arg.is_absolute() else (project_dir / out_arg).resolve()
    ensure_dir(output.parent)

    chosen = select_scenes(data['scenes'], args)
    if not chosen:
        raise StudioError('Nenhuma cena selecionada.')

    images, img_warnings = resolve_images(chosen, data, project_dir, args, w, h, fonts, output.parent)
    if args.images_only:
        print('\nPronto (--images-only). Revise as imagens; para trocar uma, use --regen N, '
              'mude o "prompt" ou aponte "image" para um arquivo seu.')
        return
    videos = resolve_videos(chosen, project_dir)

    clips, wavs, srt, chapters = [], [], [], []
    clock = 0.0
    for pos, (idx, scene) in enumerate(chosen):
        layout = layouts.detect_layout(scene)
        if layout == 'image' and idx not in images:
            layout = 'card'
        label = scene.get('title') or scene.get('headline', '')
        print(f'[{pos + 1}/{len(chosen)}] Cena {idx} ({layout}): {label}', flush=True)
        next_scene = chosen[pos + 1][1] if pos + 1 < len(chosen) else None
        entry = entry_of(scene, data)
        fade_in = pos == 0 or entry == 'fade'
        fade_out = next_scene is None or entry_of(next_scene, data) == 'fade'

        text = scene['narration'].strip()
        if args.no_voice:
            src, events = voice.silent(text, cache)
        else:
            src, events = voice.synthesize(text, voice_name, rate, cache, force=args.force_voice)
        speech = voice.audio_seconds(src)
        head = FADE + 0.1 if fade_in else 0.0
        tail = max(TAIL, FADE + 0.15) if fade_out else TAIL
        frames = math.ceil((head + speech + tail) * fps)
        total = frames / fps
        words = subtitles.align_words(text, events, speech)
        shifted = [subtitles.Word(x.text, x.start + head, x.end + head) for x in words]

        img = work / f'visual_{idx:02}.png'
        ctx = layouts.Ctx(scene, idx, w, h, theme, channel, fonts, font_name, shifted,
                          head, head + speech, total)
        styles, lay_events = [], []
        if layout == 'video':
            styles, lay_events = layouts.image_overlay(ctx)  # título opcional, como nas imagens
            kind, amount = 'video', 0.0
        elif layout == 'image':
            photo = visuals.fit_16x9(images[idx], w, h)
            visuals.finish_photo(photo, darken_top=bool(scene.get('overlay_title'))).save(img)
            styles, lay_events = layouts.image_overlay(ctx)
            kind, amount = 'image', motion_amount
        elif layout == 'card':
            visuals.make_card(scene, idx, img, w, h, channel, theme, fonts)
            kind, amount = 'card', motion_amount
        else:
            styles, lay_events = layouts.BUILDERS[layout](ctx, img)
            kind, amount = 'text', min(motion_amount, 0.035)
        amount = float(scene.get('motion_amount', amount))

        ass = work / f'legendas_{idx:02}.ass'
        subtitles.write_scene_ass(ass, shifted, scene.get('callouts'), total, w, h, font_name, accent,
                                  sub_mode, extra_styles=styles, extra_events=lay_events,
                                  font_path=fonts['bold'])
        srt.extend(subtitles.srt_blocks(shifted, clock))
        if scene.get('chapter'):
            chapters.append((clock, scene['chapter']))

        wav = work / f'audio_{idx:02}.wav'
        audio.scene_audio(src, wav, head, total)
        clip = work / f'video_{idx:02}.mp4'
        if layout == 'video':
            piece = video.prepare_clip(videos[idx], work, idx, w, h, fps, scene.get('video_start'),
                                       scene.get('video_end'), preset=args.preset)
            shade = work / f'sombra_{idx:02}.png'
            visuals.shade_overlay(w, h, darken_top=bool(scene.get('overlay_title'))).save(shade)
            video.render_video_scene(piece.name, shade.name, ass.name, clip.name, frames, w, h, fps,
                                     fade_in, fade_out, FADE, cwd=work, preset=args.preset, entry=entry)
        else:
            motion = video.pick_motion(scene.get('motion', 'auto'), idx, kind, portrait=h > w)
            video.render_scene(img.name, ass.name, clip.name, frames, w, h, fps, motion, fade_in, fade_out,
                               FADE, cwd=work, amount=amount, preset=args.preset, entry=entry)
        clips.append(clip)
        wavs.append(wav)
        clock += total

    print('Montando vídeo final...', flush=True)
    video.concat_files(clips, work / 'lista_video.txt', work / 'video_sem_audio.mp4')
    video.concat_files(wavs, work / 'lista_audio.txt', work / 'narracao.wav')
    audio.final_mix(work / 'video_sem_audio.mp4', work / 'narracao.wav', output, clock,
                    music=music, music_db=float(data.get('music_volume_db', -20)),
                    normalize=not args.no_voice)
    srt_path = output.with_suffix('.srt')
    subtitles.write_srt(srt_path, srt)
    chap_path = output.with_name(output.stem + '_capitulos.txt')
    warn = write_chapters(chap_path, chapters, clock)

    print(f'\nVídeo pronto: {output}')
    print(f'Duração: {fmt_clock(clock)} ({clock:.1f} s) | {w}x{h} @ {fps} fps | '
          f'renderizado em {time.time() - t0:.0f} s')
    print(f'Legenda para o YouTube: {srt_path}')
    if warn is not None:
        print(f'Capítulos para a descrição: {chap_path}')
        for msg in warn:
            print(f'  Atenção: {msg}')
    for msg in img_warnings:
        print(f'Atenção: {msg}')
    if args.no_voice:
        print('Atenção: modo --no-voice (áudio mudo). Serve só para testar a montagem.')


if __name__ == '__main__':
    try:
        main()
    except StudioError as err:
        sys.exit(f'\nErro: {err}')
    except KeyboardInterrupt:
        sys.exit('\nInterrompido.')
