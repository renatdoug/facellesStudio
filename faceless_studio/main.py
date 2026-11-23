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

from studio import __version__, align, audio, images_ai, layouts, subtitles, toon, video, visuals, voice
from studio.util import StudioError, check_ffmpeg, ensure_dir

ROOT = Path(__file__).resolve().parent
FADE = 0.4
TAIL = 0.2  # pausa padrão depois da fala (campo "pause" do roteiro)


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
    p.add_argument('--align-model', default=align.DEFAULT_MODEL,
                   help='Modelo local que alinha as palavras de vozes GRAVADAS (campo "audio"): tiny, base, small, medium')
    p.add_argument('--recording-sheet', metavar='PERSONAGEM',
                   help='Lista as falas de um personagem para gravar (com o nome sugerido de cada arquivo) e para')
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
    pause = data.get('pause')
    if pause is not None and (isinstance(pause, bool) or not isinstance(pause, (int, float)) or not 0 <= pause <= 3):
        raise StudioError('"pause" deve ser um número de segundos entre 0 e 3 (pausa depois da fala de cada cena).')
    if data.get('subtitles', 'karaoke') not in subtitles.CAPTION_MODES:
        raise StudioError('"subtitles" deve ser ' + ', '.join(subtitles.CAPTION_MODES) + '.')
    if 'resolution' in data and not re.fullmatch(r'\d{3,5}x\d{3,5}', str(data['resolution']).lower()):
        raise StudioError('"resolution" deve ter o formato LARGURAxALTURA, ex.: 1920x1080 ou 1080x1920.')
    if 'toon' in data:
        try:
            toon.validate_toon(data['toon'])
        except ValueError as err:
            raise StudioError(str(err))
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
        if layouts.detect_layout(s) == 'toon':
            try:
                toon.validate_scene(s, data.get('toon'), n)
            except ValueError as err:
                raise StudioError(str(err))
        if s.get('voice') is not None and not re.fullmatch(r'[a-z]{2}-[A-Z]{2}-[A-Za-z]+Neural', str(s['voice'])):
            raise StudioError(f'Cena {n}: "voice" inválida (ex.: pt-BR-FranciscaNeural).')
        if s.get('audio') is not None and not (isinstance(s['audio'], str) and s['audio'].strip()):
            raise StudioError(f'Cena {n}: "audio" deve ser o caminho de um arquivo de áudio (voz gravada).')
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
            if not str(scene.get('prompt') or '').strip():  # nunca gera (e cobra) imagem sem descrição
                raise StudioError(f'Cena {idx}: o tipo é "imagem", mas o "prompt" está vazio. '
                                  f'Descreva a imagem ou troque o tipo da cena.')
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


def resolve_recordings(chosen, script_dir, cache, args):
    """Voz gravada (campo "audio"): confere os arquivos e ALINHA as palavras de todas as cenas gravadas antes de
    renderizar qualquer coisa. Devolve {nº da cena: (wav, eventos, relatório)}. Alinhamento sem confiança interrompe
    o processo, dizendo qual cena e por quê (nunca renderiza uma sincronização errada como se fosse boa)."""
    found, problems = {}, []
    for idx, scene in chosen:
        if not scene.get('audio') or args.no_voice:
            continue
        src = Path(scene['audio'])
        src = (src if src.is_absolute() else (script_dir / src)).resolve()
        if not src.is_file():
            raise StudioError(f'Áudio da cena {idx} não encontrado: {src}')
        print(f'Cena {idx}: voz gravada "{src.name}" — alinhando as palavras...', flush=True)
        wav, events, probs, source = voice.recorded(src, cache, args.align_model)
        rep = align.assess(scene['narration'], events, probs, source, voice.audio_seconds(wav))
        print(f'  {rep.summary()}', flush=True)
        for msg in rep.messages:
            print(f'  Atenção: {msg}', flush=True)
        if rep.level == 'erro':
            problems.append(f'Cena {idx} ("{src.name}"): ' + ' '.join(rep.messages))
        found[idx] = (wav, events, rep)
    if problems:
        raise StudioError('A sincronização da voz gravada não é confiável, então nada foi renderizado:\n  - '
                          + '\n  - '.join(problems)
                          + '\nConfira se o áudio é desta cena e se o "narration" é o que foi dito (a legenda usa o texto do '
                            'roteiro), ou forneça os tempos em "<áudio>.palavras.json".')
    return found


def _span(spans, idx):
    a, b = spans.get(idx, (0.0, 0.0))
    return f'{a:.1f}s a {b:.1f}s'


def alignment_review(recordings):
    """Cenas de voz gravada cujo alinhamento NÃO é bom (precisam de conferência antes de publicar)."""
    return sorted(i for i, (_, _, r) in recordings.items() if r.level != 'ok')


def write_alignment_report(path, recordings, spans):
    """Relatório ao lado do vídeo: por cena gravada, se a sincronização (boca e legendas) é confiável."""
    review = alignment_review(recordings)
    lines = ['Alinhamento da voz gravada', '']
    if review:
        lines += ['*** CONFERIR ANTES DE PUBLICAR: cenas ' + ', '.join(map(str, review)) + ' ***',
                  'Assista a esses trechos: a boca e as legendas podem estar fora do tempo da voz.', '']
    else:
        lines += ['Todas as cenas gravadas com alinhamento OK.', '']
    for idx in sorted(recordings):
        rep = recordings[idx][2]
        lines.append(f'Cena {idx} ({_span(spans, idx)}): {rep.summary()}')
        lines += [f'    - {msg}' for msg in rep.messages]
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return path


def print_alignment_summary(recordings, spans, report_path):
    review = alignment_review(recordings)
    if not review:
        print(f'Voz gravada: alinhamento OK em todas as cenas ({report_path.name}).')
        return
    bar = '=' * 62
    print(f'\n{bar}\n CONFERIR ANTES DE PUBLICAR: alinhamento da voz gravada\n{bar}')
    for idx in review:
        rep = recordings[idx][2]
        print(f' Cena {idx} ({_span(spans, idx)}): {rep.summary()}')
        for msg in rep.messages:
            print(f'    - {msg}')
    print(f' Assista a esses trechos: a boca e as legendas podem estar fora do tempo.\n Relatório: {report_path}\n{bar}')


def print_recording_sheet(data, speaker, script):
    chars = (data.get('toon') or {}).get('characters') or {}
    if speaker not in chars:
        raise StudioError(f'"{speaker}" não é um personagem do roteiro ({", ".join(chars) or "nenhum"}).')
    rows = align.recording_sheet(data['scenes'], speaker)
    if not rows:
        raise StudioError(f'O personagem "{speaker}" não fala em nenhuma cena.')
    lines = [f'Falas de {speaker} para gravar (um arquivo por fala; salve em "audio/" ao lado do roteiro):', '']
    for n, sid, fname, text in rows:
        lines += [f'Cena {n} [{sid}]  ->  audio/{fname}', f'    "{text}"', '']
    lines += ['Dicas: fale como numa conversa, em ambiente silencioso, com 15-20 cm do microfone; deixe ~0,5 s de silêncio antes e depois.',
              'Depois, em cada cena, preencha o campo "audio": "audio/<arquivo>".']
    text = '\n'.join(lines)
    print(text)
    sheet = script.with_name(f'gravacao_{speaker}.txt')
    sheet.write_text(text + '\n', encoding='utf-8')
    print(f'\n(salvo em {sheet})')


def main():
    args = parse_args()
    t0 = time.time()
    if args.recording_sheet:
        script = (ROOT / args.script).resolve()
        print_recording_sheet(load_script(script), args.recording_sheet, script)
        return
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
    pause = float(data.get('pause', TAIL))

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
    recordings = resolve_recordings(chosen, project_dir, cache, args)
    toon_stage, toon_seen, toon_prev = None, False, None
    if any(layouts.detect_layout(s) == 'toon' for _, s in chosen):
        cfg = data['toon']
        try:
            toon_stage = toon.Stage(w, h, cfg['characters'], cfg.get('background', 'room'), base_dir=project_dir,
                                    font_path=fonts['bold'])
        except FileNotFoundError as err:
            raise StudioError(str(err))

    clips, wavs, srt, chapters = [], [], [], []
    clock = 0.0
    spans = {}  # nº da cena -> (início, fim) no vídeo final, para o relatório de alinhamento
    for pos, (idx, scene) in enumerate(chosen):
        layout = layouts.detect_layout(scene)
        if layout == 'image' and idx not in images:
            layout = 'card'
        label = scene.get('title') or scene.get('headline', '')
        print(f'[{pos + 1}/{len(chosen)}] Cena {idx} ({layout}): {label}', flush=True)
        next_scene = chosen[pos + 1][1] if pos + 1 < len(chosen) else None
        entry = entry_of(scene, data)
        # Primeira cena: com "punch" ou "flash" o vídeo começa NA HORA (sem 0,5 s de tela preta e silêncio),
        # que é o que um gancho de Short precisa. Com "cut" ou "fade" continua a entrada suave do preto.
        instant = pos == 0 and entry in ('punch', 'flash')
        fade_in = (pos == 0 and not instant) or entry == 'fade'
        fade_out = next_scene is None or entry_of(next_scene, data) == 'fade'

        text = scene['narration'].strip()
        # voz da cena: "voice" da cena > voz do personagem que fala > voz do roteiro
        chars = (data.get('toon') or {}).get('characters') or {}
        scene_voice = scene.get('voice') or (chars.get(scene.get('speaker')) or {}).get('voice') or voice_name
        if args.no_voice:
            src, events = voice.silent(text, cache)
        elif idx in recordings:  # voz GRAVADA: tempos do alinhador local, nunca do edge-tts
            src, events, _ = recordings[idx]
        else:
            src, events = voice.synthesize(text, scene_voice, rate, cache, force=args.force_voice)
        speech = voice.audio_seconds(src)
        if not args.no_voice:  # corta o silêncio que o edge-tts deixa depois da última palavra
            speech = voice.speech_seconds(src, events, speech)
        head = FADE + 0.1 if fade_in else 0.0
        tail = max(pause, FADE + 0.15) if fade_out else pause
        frames = math.ceil((head + speech + tail) * fps)
        total = frames / fps
        words = subtitles.align_words(text, events, speech, fuzzy=idx in recordings)
        shifted = [subtitles.Word(x.text, x.start + head, x.end + head) for x in words]

        img = work / f'visual_{idx:02}.png'
        ctx = layouts.Ctx(scene, idx, w, h, theme, channel, fonts, font_name, shifted,
                          head, head + speech, total, instant=instant)
        styles, lay_events = [], []
        if layout == 'video':
            styles, lay_events = layouts.image_overlay(ctx)  # título opcional, como nas imagens
            kind, amount = 'video', 0.0
        elif layout == 'toon':
            kind, amount = 'toon', 0.0  # sem layout de texto: os bonecos são desenhados quadro a quadro
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
                                  font_path=fonts['bold'],
                                  # cenas de texto têm o nome do canal no canto superior: a tarja desce para não cobri-lo
                                  callout_top=0.10 if layout in ('image', 'video') else 0.14)
        srt.extend(subtitles.srt_blocks(shifted, clock, total))
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
        elif layout == 'toon':
            camera = scene.get('camera', 'auto')
            if camera == 'auto':  # 1º plano aberto (mostra os dois); depois fecha em quem fala; ilustração na parede = aberto
                camera = 'speaker' if toon_seen and not scene.get('demo') else 'wide'
            toon_seen = True
            quadros = toon_stage.scene_frames(scene['speaker'], shifted, frames, fps, scene.get('emotion', 'neutral'),
                                              scene.get('reaction', 'neutral'), scene.get('gesture', 'none'), camera,
                                              seed=idx, prev=toon_prev, demo=scene.get('demo'),
                                              demo_at=scene.get('demo_at'))
            toon_prev = (camera, scene['speaker'])  # a próxima cena de cartum desliza a câmera a partir daqui
            video.render_frames(quadros, ass.name, clip.name, frames, w, h, fps, fade_in, fade_out, FADE, cwd=work,
                                preset=args.preset, entry=entry)
        else:
            motion = video.pick_motion(scene.get('motion', 'auto'), idx, kind, portrait=h > w)
            video.render_scene(img.name, ass.name, clip.name, frames, w, h, fps, motion, fade_in, fade_out,
                               FADE, cwd=work, amount=amount, preset=args.preset, entry=entry)
        clips.append(clip)
        wavs.append(wav)
        spans[idx] = (clock, clock + total)
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
    if recordings:
        report_path = write_alignment_report(output.with_name(output.stem + '_alinhamento.txt'), recordings, spans)
        print_alignment_summary(recordings, spans, report_path)
    if args.no_voice:
        print('Atenção: modo --no-voice (áudio mudo). Serve só para testar a montagem.')


if __name__ == '__main__':
    try:
        main()
    except StudioError as err:
        sys.exit(f'\nErro: {err}')
    except KeyboardInterrupt:
        sys.exit('\nInterrompido.')
