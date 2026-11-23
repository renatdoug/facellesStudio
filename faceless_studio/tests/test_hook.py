"""Gancho: a primeira cena com punch/flash começa na hora e já tem título e número no 1º quadro."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from studio import layouts, subtitles, visuals

ROOT = Path(__file__).resolve().parent.parent
needs_ffmpeg = pytest.mark.skipif(not (shutil.which('ffmpeg') and shutil.which('ffprobe')),
                                  reason='FFmpeg não encontrado')


def make_ctx(scene, instant, w=1080, h=1920):
    fonts = {'bold': visuals.find_font(True), 'regular': visuals.find_font(False)}
    words = [subtitles.Word(t, i * 0.3, (i + 1) * 0.3) for i, t in enumerate('Quase metade das admissões'.split())]
    return layouts.Ctx(scene, 1, w, h, 'health', 'Canal', fonts, visuals.font_family(fonts['bold']), words,
                       0.0 if instant else 0.5, 1.5, 2.0, instant=instant)


def dialogues(evs, style):
    return [e for e in evs if f',{style},' in e]


def test_titulo_nao_tem_fade_quando_a_cena_abre_na_hora():
    scene = {'headline': 'VOCÊ SABIA?'}
    _, normal, _ = layouts._headline_events(make_ctx(scene, instant=False))
    _, instant, _ = layouts._headline_events(make_ctx(scene, instant=True))
    assert '\\fad(300,0)' in dialogues(normal, 'LHead')[0] and '\\fad(300,0)' in dialogues(normal, 'LShape')[0]
    assert '\\fad' not in dialogues(instant, 'LHead')[0] and '\\fad' not in dialogues(instant, 'LShape')[0]


def test_numero_com_at_zero_aparece_no_primeiro_quadro(tmp_path):
    scene = {'headline': 'X', 'number': {'value': 42, 'suffix': '%', 'at': 0}}
    _, evs = layouts.layout_number(make_ctx(scene, instant=True), tmp_path / 'bg.png')
    first = dialogues(evs, 'LBig')[0]
    assert first.split(',')[1] == '0:00:00.00'  # começa em 0 s
    assert '\\fad' not in first  # e sem fade de entrada: o 1º quadro já mostra o número
    # com "on_word" (comportamento anterior) o número só entra quando a palavra é dita
    scene = {'headline': 'X', 'number': {'value': 42, 'on_word': 'metade'}}
    _, evs = layouts.layout_number(make_ctx(scene, instant=False), tmp_path / 'bg.png')
    assert dialogues(evs, 'LBig')[0].split(',')[1] != '0:00:00.00'


def frame_stats(path, t, w=108, h=192):
    """(brilho médio 0-255, nº de pixels quase brancos) do quadro em t segundos."""
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{t:.3f}', '-i', str(path), '-frames:v', '1', '-vf',
                          f'scale={w}:{h}', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                         capture_output=True, check=True).stdout
    px = [raw[i:i + 3] for i in range(0, len(raw), 3)]
    return sum(sum(p) for p in px) / (3 * len(px)), sum(1 for p in px if min(p) > 200)


def duration(path):
    return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of',
                                 'default=nw=1:nk=1', str(path)], capture_output=True, text=True,
                                check=True).stdout)


def render(tmp_path, entry, name):
    script = {'channel': 'T', 'theme': 'health', 'fps': 25, 'resolution': '360x640', 'subtitles': 'pop',
              'images': {'provider': 'none'},
              'scenes': [{'headline': 'VOCÊ SABIA?', 'transition': entry, 'narration': 'Quase metade das admissões.',
                          'number': {'value': 42, 'suffix': '%', 'at': 0}},
                         {'headline': 'FIM', 'transition': 'cut', 'narration': 'Segunda cena.'}]}
    path = tmp_path / f'{name}.json'
    path.write_text(json.dumps(script), encoding='utf-8')
    done = subprocess.run([sys.executable, str(ROOT / 'main.py'), '--script', str(path), '--no-voice', '--preset',
                           'ultrafast', '--output', f'output/{name}.mp4'], capture_output=True, text=True,
                          encoding='utf-8', errors='replace')
    assert done.returncode == 0, done.stdout + done.stderr
    return tmp_path / 'output' / f'{name}.mp4'


@needs_ffmpeg
def test_primeira_cena_com_punch_ou_flash_comeca_na_hora(tmp_path):
    cut = render(tmp_path, 'cut', 'cut')        # comportamento de sempre: entra do preto
    punch = render(tmp_path, 'punch', 'punch')  # gancho: sem preto, sem silêncio de entrada
    flash = render(tmp_path, 'flash', 'flash')
    # ~0,5 s a menos de tela preta e silêncio (a entrada em fade tem 0,5 s)
    assert duration(cut) - duration(punch) == pytest.approx(0.5, abs=0.1)
    assert duration(cut) - duration(flash) == pytest.approx(0.5, abs=0.1)
    # logo no começo, "cut" ainda está quase preto (fade); "punch" já mostra o título em branco
    cut_bright, cut_white = frame_stats(cut, 0.04)
    punch_bright, punch_white = frame_stats(punch, 0.04)
    assert punch_white > 150 and cut_white < 20, (cut_white, punch_white)
    assert punch_bright > cut_bright + 10


def test_cena_de_imagem_sem_prompt_nao_gera_nem_cobra(tmp_path):
    """Prompt apagado no editor: o motor para antes de chamar qualquer fornecedor de imagem."""
    script = {'channel': 'T', 'images': {'provider': 'gemini'},
              'scenes': [{'layout': 'image', 'prompt': '   ', 'narration': 'Olá.'}]}
    path = tmp_path / 'r.json'
    path.write_text(json.dumps(script), encoding='utf-8')
    done = subprocess.run([sys.executable, str(ROOT / 'main.py'), '--script', str(path), '--images-only'],
                          capture_output=True, text=True, encoding='utf-8', errors='replace')
    assert done.returncode != 0 and 'prompt' in (done.stdout + done.stderr)
    assert not (tmp_path / 'assets' / 'generated' / 'manifest.json').exists()  # nada foi gerado


def test_tarja_nao_cobre_o_nome_do_canal_nas_cenas_de_texto(tmp_path):
    """A tarja ("callout") desce nas cenas com o nome do canal no canto; nas de imagem fica no alto."""
    words = [subtitles.Word('Siga', 0, 0.3), subtitles.Word('o', 0.3, 0.5), subtitles.Word('canal', 0.5, 0.9)]

    def margin_v(top):
        path = tmp_path / f'c{top}.ass'
        subtitles.write_scene_ass(path, words, [{'text': 'Siga o canal', 'at': 0.3}], 3, 1080, 1920, 'Arial',
                                  (103, 233, 208), callout_top=top)
        line = [ln for ln in path.read_text(encoding='utf-8').splitlines() if ln.startswith('Style: Callout')][0]
        return int(line.split(',')[-2])  # MarginV
    assert margin_v(0.10) == round(1920 * 0.10) and margin_v(0.14) == round(1920 * 0.14)
    assert margin_v(0.14) > 1920 * 0.03 + 1920 * 0.10  # abaixo do rótulo do canal (0,10 h + altura da fonte)


def test_escurecimento_da_base_cobre_a_legenda_no_vertical():
    """A legenda vertical fica em ~75% da altura: ali o escurecimento precisa ser forte (no horizontal não muda)."""
    def alpha_at(w, h, frac):
        return visuals.shade_overlay(w, h).getpixel((w // 2, int(h * frac)))[3] / 255
    assert alpha_at(1080, 1920, 0.75) > 0.55      # antes: ~0,17
    assert alpha_at(1080, 1920, 0.45) < 0.02      # o meio da imagem continua limpo
    assert alpha_at(1080, 1920, 0.95) == pytest.approx(0.70, abs=0.03)
    assert alpha_at(1920, 1080, 0.75) < 0.25      # horizontal: degradê original
    assert alpha_at(1920, 1080, 0.95) > 0.5
