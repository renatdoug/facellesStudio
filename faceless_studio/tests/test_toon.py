"""Bonecos animados (cartum): boca sincronizada, piscar, câmera, validação e renderização de verdade."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageOps

import main as engine
from studio import layouts, subtitles, toon, visuals
from studio.util import StudioError

ROOT = Path(__file__).resolve().parent.parent
needs_ffmpeg = pytest.mark.skipif(not (shutil.which('ffmpeg') and shutil.which('ffprobe')),
                                  reason='FFmpeg não encontrado')


def words(text, start=0.3, step=0.4, dur=0.34):
    return [subtitles.Word(t, start + i * step, start + i * step + dur) for i, t in enumerate(text.split())]


# ------------------------------------------------------------------ boca, piscar, olhar, gestos

def test_boca_so_abre_enquanto_a_palavra_e_falada_e_abre_e_fecha_por_silaba():
    ws = words('Eu vi num ninja extraordinário', start=1.0)
    for t in (0.0, 0.5, 0.95):                       # antes da 1ª palavra: fechada
        assert toon.mouth_open(ws, t) == 0.0
    assert toon.mouth_open(ws, ws[-1].end + 0.2) == 0.0  # depois da última: fechada
    # numa palavra comprida (6 sílabas) a boca faz vários ciclos: abre e fecha de verdade
    w = ws[-1]
    series = [toon.mouth_open(ws, w.start + (w.end - w.start) * i / 120) for i in range(121)]
    peaks = sum(1 for a, b, c in zip(series, series[1:], series[2:]) if b > a and b >= c and b > 0.3)
    assert peaks >= 4 and min(series) < 0.05 and max(series) > 0.5
    # mesma entrada => mesma boca (determinístico: o vídeo é reproduzível)
    assert toon.mouth_open(ws, 1.1, 's') == toon.mouth_open(ws, 1.1, 's')


def test_piscar_e_deterministico_e_muda_com_a_semente():
    spec = toon.character_spec('ana', None, 0)
    a, b = toon.Actor('ana', spec, [], seed=1), toon.Actor('ana', spec, [], seed=1)
    ts = [i / 30 for i in range(30 * 12)]
    sa = [a.pose(t)['blink'] for t in ts]
    assert sa == [b.pose(t)['blink'] for t in ts]
    assert max(sa) == 1.0  # o olho chega a fechar de verdade, em 30 quadros por segundo
    assert 3 <= sum(1 for x, y in zip(sa, sa[1:]) if x == 0 and y > 0) <= 6  # piscadas esparsas
    for fps in (24, 25, 30, 60):  # em qualquer taxa de quadros
        assert max(toon.Actor('ana', spec, [], seed=1).pose(i / fps)['blink'] for i in range(fps * 8)) == 1.0
    assert sa != [toon.Actor('ana', spec, [], seed=2).pose(t)['blink'] for t in ts]


def test_ouvinte_nao_fala_e_olha_para_quem_fala():
    spec = toon.character_spec('leo', None, 1)
    ouvinte = toon.Actor('leo', spec, [], emotion='neutral')
    for t in (0.0, 0.7, 1.9, 3.1):
        p = ouvinte.pose(t)
        assert p['mouth'] == 0.0 and p['look'][0] > 0.7 and p['gesture'][2] == 0.0
    falante = toon.Actor('leo', spec, words('Eu vi um ninja correndo na água'), emotion='happy', gesture='point')
    p = falante.pose(1.0)
    assert p['gesture'][:2] == ('down', 'point') and p['gesture'][2] > 0.9


def test_emocao_muda_sobrancelha_e_pausa_do_olho():
    spec = toon.character_spec('ana', None, 0)
    angry = toon.Actor('ana', spec, [], emotion='angry').pose(1.0)['emotion']
    sad = toon.Actor('ana', spec, [], emotion='sad').pose(1.0)['emotion']
    surprised = toon.Actor('ana', spec, [], emotion='surprised').pose(1.0)['emotion']
    assert angry['brow'] < -0.8 and sad['brow'] > 0.8 and surprised['eye'] > 1.2 and surprised['lift'] > 10
    # começa neutra e vai para a emoção (transição suave, não um salto)
    at0 = toon.Actor('ana', spec, [], emotion='angry').pose(0.0)['emotion']
    assert at0['brow'] == pytest.approx(toon.EMOTIONS['neutral']['brow'], abs=0.05)
    assert toon.Actor('ana', spec, [], emotion='inexistente').emotion_name == 'neutral'


# ------------------------------------------------------------------ personagem, cenário e câmera

def test_fichas_padrao_sao_diferentes_e_lado_padrao_e_esquerda_direita():
    a, b = toon.character_spec('ana', None, 0), toon.character_spec('leo', None, 1)
    assert (a['side'], b['side']) == ('left', 'right') and a['hair'] != b['hair'] and a['shirt'] != b['shirt']
    c = toon.character_spec('x', {'hair': 'bob', 'shirt': [10, 20, 30]}, 0)
    assert c['hair'] == 'bob' and c['shirt'] == [10, 20, 30] and c['pants'] == a['pants']  # o resto usa o padrão


def test_desenho_do_personagem_e_independente_do_cenario_e_espelha():
    spec = toon.character_spec('ana', None, 0)
    pose = toon.Actor('ana', spec, []).pose(0.5)
    right = toon.draw_character(spec, pose, 1.0, facing=1)
    left = toon.draw_character(spec, pose, 1.0, facing=-1)
    assert right.mode == 'RGBA' and right.getbbox() is not None
    assert ImageChops.difference(left, ImageOps.mirror(right)).getbbox(alpha_only=False) is None
    assert ImageChops.difference(left, right).getbbox(alpha_only=False) is not None  # não é simétrico (cabelo, braço)
    # trocar a cor da camisa muda só o personagem (nenhum cenário envolvido)
    other = toon.draw_character({**spec, 'shirt': [20, 20, 20]}, pose, 1.0)
    assert ImageChops.difference(other, right).getbbox(alpha_only=False) is not None


def test_palco_gera_quadros_na_resolucao_e_a_camera_segue_quem_fala():
    stage = toon.Stage(270, 480, {'ana': {}, 'leo': {}}, ss=2)
    ws = words('Olá pessoal tudo bem')
    a_ana = stage.scene_actors('ana', ws)
    a_leo = stage.scene_actors('leo', ws)
    f_wide = stage.frame(a_ana, 'ana', 0.5, 3.0, 'wide')
    f_ana, f_leo = stage.frame(a_ana, 'ana', 0.5, 3.0, 'speaker'), stage.frame(a_leo, 'leo', 0.5, 3.0, 'speaker')
    assert f_wide.size == f_ana.size == f_leo.size == (270, 480)
    assert ImageChops.difference(f_ana, f_leo).getbbox() and ImageChops.difference(f_wide, f_ana).getbbox()
    # a câmera nunca sai do cenário, mesmo no personagem da ponta
    for who in ('ana', 'leo'):
        x0, y0, x1, y1 = stage._camera('speaker', who, 1.0, 3.0)
        assert 0 <= x0 < x1 <= 270 * 2 and 0 <= y0 < y1 <= 480 * 2
    frames = list(stage.scene_frames('ana', ws, 6, 30))
    assert len(frames) == 6 and len(frames[0]) == 270 * 480 * 3 and len(set(frames)) > 1  # quadros diferentes: há movimento


def test_cenario_proprio_e_cenario_inexistente(tmp_path):
    Image.new('RGB', (300, 200), (90, 120, 160)).save(tmp_path / 'sala.png')
    stage = toon.Stage(120, 200, {'ana': {}}, background='sala.png', ss=1, base_dir=tmp_path)
    assert stage.bg.size == (120, 200) and stage.bg.getpixel((5, 5))[2] > stage.bg.getpixel((5, 5))[0]
    with pytest.raises(FileNotFoundError):
        toon.Stage(120, 200, {'ana': {}}, background='nao_existe.png', ss=1, base_dir=tmp_path)
    assert toon.Stage(120, 200, {'a': {}}, background='plain', ss=1).bg.size == (120, 200)


# ------------------------------------------------------------------ validação (mensagens com cena e campo)

BASE = {'toon': {'characters': {'ana': {'voice': 'pt-BR-FranciscaNeural'}, 'leo': {}}},
        'scenes': [{'speaker': 'ana', 'narration': 'Oi.'}, {'speaker': 'leo', 'narration': 'Olá.', 'emotion': 'happy',
                                                            'gesture': 'point', 'camera': 'wide'}]}


def test_roteiro_de_cartum_valido_passa_e_e_detectado_como_cartum():
    engine.validate_script(BASE)
    assert [layouts.detect_layout(s) for s in BASE['scenes']] == ['toon', 'toon']
    assert 'toon' in layouts.LAYOUTS and 'topbox' in subtitles.CAPTION_MODES


@pytest.mark.parametrize('mudanca, trecho', [
    (lambda d: d['scenes'][0].update(speaker='zeca'), 'Cena 1.*zeca.*toon.characters'),
    (lambda d: d['scenes'][1].update(emotion='furioso'), 'Cena 2.*emotion'),
    (lambda d: d['scenes'][1].update(gesture='dancar'), 'Cena 2.*gesture'),
    (lambda d: d['scenes'][1].update(camera='drone'), 'Cena 2.*camera'),
    (lambda d: d['scenes'][1].update(reaction='x'), 'Cena 2.*reaction'),
    (lambda d: d['scenes'][0].update(voice='voz ruim'), 'Cena 1.*voice'),
    (lambda d: d['toon']['characters'].update(zeca={}), 'até 2 personagens'),
    (lambda d: d['toon']['characters']['ana'].update(hair='moicano'), 'ana.*hair'),
    (lambda d: d['toon']['characters']['ana'].update(shirt=[1, 2]), 'ana.*shirt'),
    (lambda d: d['toon']['characters']['ana'].update(side='meio'), 'ana.*side'),
    (lambda d: d['toon']['characters']['ana'].update(voice='x'), 'ana.*voice'),
    (lambda d: d.pop('toon'), 'Cena 1.*toon'),
    (lambda d: d.update(toon={'characters': {}}), 'pelo menos um personagem'),
])
def test_erros_do_cartum_dizem_cena_e_campo(mudanca, trecho):
    data = json.loads(json.dumps(BASE))
    mudanca(data)
    with pytest.raises(StudioError, match=trecho):
        engine.validate_script(data)


def test_legenda_em_caixa_preta_no_topo_com_a_frase_inteira(tmp_path):
    fonts = visuals.find_font(True)
    ws = words('Isto é uma frase bastante longa para precisar quebrar em mais de uma linha dentro da caixa', 0.5, 0.3)
    path = tmp_path / 'c.ass'
    subtitles.write_scene_ass(path, ws, None, 8.0, 1080, 1920, 'Arial', (255, 255, 255), 'topbox', font_path=fonts)
    ass = path.read_text(encoding='utf-8')
    style = [ln for ln in ass.splitlines() if ln.startswith('Style: Sub')][0].split(',')
    assert style[15] == '3' and style[18] == '8'  # BorderStyle 3 (caixa), Alignment 8 (topo)
    dialog = [ln for ln in ass.splitlines() if ln.startswith('Dialogue') and ',Sub,' in ln]
    assert len(dialog) == 1 and '\\N' in dialog[0] and 'caixa' in dialog[0] and dialog[0].startswith('Dialogue: 0,0:00:00.45')
    m = subtitles.caption_metrics(1080, 1920, 'topbox')
    assert m['margin_v'] > 1920 * 0.1  # abaixo da barra superior do Shorts


# ------------------------------------------------------------------ renderização de verdade

def probe(path, entries):
    return subprocess.run(['ffprobe', '-v', 'error', *entries, '-of', 'csv=p=0', str(path)],
                          capture_output=True, text=True, check=True).stdout.strip()


def frame_gray(path, t, crop):
    w, h, x, y = crop
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{t:.3f}', '-i', str(path), '-frames:v', '1', '-vf',
                          f'crop={w}:{h}:{x}:{y}', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'],
                         capture_output=True, check=True).stdout
    return raw


@needs_ffmpeg
def test_video_de_cartum_com_boca_em_movimento_legenda_no_topo_e_duas_vozes_no_roteiro(tmp_path):
    script = {'channel': 'T', 'fps': 25, 'resolution': '360x640', 'subtitles': 'topbox', 'images': {'provider': 'none'},
              'toon': BASE['toon'],
              'scenes': [{'speaker': 'ana', 'emotion': 'happy', 'gesture': 'open',
                          'narration': 'Eu vi um ninja correndo sobre a água.'},
                         {'speaker': 'leo', 'emotion': 'surprised', 'reaction': 'smug',
                          'narration': 'Será que isso funciona de verdade?'}]}
    path = tmp_path / 'r.json'
    path.write_text(json.dumps(script), encoding='utf-8')
    done = subprocess.run([sys.executable, str(ROOT / 'main.py'), '--script', str(path), '--no-voice', '--preset',
                           'ultrafast'], capture_output=True, text=True, encoding='utf-8', errors='replace')
    assert done.returncode == 0, done.stdout + done.stderr
    final = tmp_path / 'output' / 'video_final.mp4'
    assert probe(final, ['-select_streams', 'v:0', '-show_entries', 'stream=width,height']) == '360,640'
    assert 'Cena 1 (toon)' in done.stdout and 'Cena 2 (toon)' in done.stdout
    # a legenda em caixa preta aparece no topo (faixa 8% a 22% da altura tem pixels bem escuros)
    top = frame_gray(final, 1.0, (360, 90, 0, 50))
    assert sum(1 for b in top if b < 30) > 400
    # o boneco se mexe: quadros consecutivos na região do rosto (cena 1 em plano aberto) são diferentes
    quadros = {frame_gray(final, 0.5 + i * 0.08, (200, 140, 160, 220)) for i in range(10)}
    assert len(quadros) >= 6, len(quadros)
    # mudou o enquadramento da cena 1 (plano aberto) para a 2 (close em quem fala)
    wide = frame_gray(final, 0.4, (360, 640, 0, 0))
    close = frame_gray(final, probe(tmp_path / 'temp' / 'video_01.mp4', ['-show_entries', 'format=duration']) and
                       float(probe(tmp_path / 'temp' / 'video_01.mp4', ['-show_entries', 'format=duration'])) + 0.4,
                       (360, 640, 0, 0))
    diff = sum(abs(a - b) for a, b in zip(wide, close)) / len(wide)
    assert diff > 6, diff


@needs_ffmpeg
def test_cenario_inexistente_vira_erro_amigavel_antes_de_renderizar(tmp_path):
    script = {'channel': 'T', 'images': {'provider': 'none'},
              'toon': {'background': 'sala_que_nao_existe.png', 'characters': {'ana': {}}},
              'scenes': [{'speaker': 'ana', 'narration': 'Oi.'}]}
    path = tmp_path / 'r.json'
    path.write_text(json.dumps(script), encoding='utf-8')
    done = subprocess.run([sys.executable, str(ROOT / 'main.py'), '--script', str(path), '--no-voice'],
                          capture_output=True, text=True, encoding='utf-8', errors='replace',
                          env={**__import__('os').environ, 'PYTHONIOENCODING': 'utf-8'})
    assert done.returncode != 0 and 'Cenário não encontrado' in (done.stdout + done.stderr)
    assert 'Traceback' not in done.stderr
