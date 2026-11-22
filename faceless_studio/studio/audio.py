"""Áudio: narração por cena com duração exata, trilha com ducking e normalização para o YouTube."""
from .util import run

RATE = 48000


def scene_audio(src, out, head, total):
    """Converte a narração para WAV 48 kHz estéreo, com `head` s de silêncio antes
    e completando até exatamente `total` s (mantém áudio e vídeo sincronizados)."""
    ms = int(round(head * 1000))
    af = f'adelay={ms}:all=1,apad,atrim=0:{total:.6f}' if ms else f'apad,atrim=0:{total:.6f}'
    run(['ffmpeg', '-y', '-loglevel', 'error', '-i', src, '-af', af,
         '-ar', RATE, '-ac', 2, '-c:a', 'pcm_s16le', out])


def final_mix(video, narration, out, total, music=None, music_db=-20.0, normalize=True):
    """Mux final. Com trilha: a música baixa sozinha quando há voz (sidechain) e faz
    fade in/out. Loudness alvo de -14 LUFS (referência do YouTube)."""
    cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-i', video, '-i', narration]
    norm = ',loudnorm=I=-14:TP=-1.5:LRA=11' if normalize else ''
    if music:
        cmd += ['-stream_loop', '-1', '-i', music]
        fade_out = max(0.0, total - 3)
        fc = (f'[1:a]aformat=sample_rates={RATE}:channel_layouts=stereo,asplit=2[nar][sc];'
              f'[2:a]aformat=sample_rates={RATE}:channel_layouts=stereo,atrim=0:{total:.3f},'
              f'volume={music_db}dB,afade=t=in:d=1.5,afade=t=out:st={fade_out:.3f}:d=3[mus];'
              '[mus][sc]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=450[duck];'
              f'[nar][duck]amix=inputs=2:duration=first:normalize=0{norm},aresample={RATE}[a]')
    else:
        fc = f'[1:a]anull{norm},aresample={RATE}[a]'
    cmd += ['-filter_complex', fc, '-map', '0:v', '-map', '[a]', '-c:v', 'copy',
            '-c:a', 'aac', '-b:a', '192k', '-t', f'{total:.3f}', '-movflags', '+faststart', out]
    run(cmd)
