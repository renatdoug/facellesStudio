"""Personagens por RECORTES (imagens criadas uma vez, animadas por código): recorte, expressões, boca, piscar, inclinação,
integração no palco e no motor, e compatibilidade com os personagens desenhados por código.
Os testes usam uma personagem SINTÉTICA desenhada aqui (nenhum arquivo externo, nenhuma chamada ao Gemini)."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageChops, ImageDraw

import main as engine
from studio import cutout, subtitles, toon
from studio.util import StudioError

ROOT = Path(__file__).resolve().parent.parent
needs_ffmpeg = pytest.mark.skipif(not (shutil.which('ffmpeg') and shutil.which('ffprobe')), reason='FFmpeg não encontrado')

W, H = 400, 600
MAGENTA = (253, 40, 253)
BOXES = {'face': [110, 100, 290, 320], 'mouth': [160, 240, 240, 290], 'eye_l': [135, 160, 195, 200], 'eye_r': [205, 160, 265, 200]}
SKIN, CARDIGAN = (214, 156, 118), (205, 150, 40)


def draw_figure(expression='neutra'):
    """Personagem de teste: cabeça, olhos, boca e corpo, sobre fundo magenta. Só a expressão muda entre as imagens."""
    im = Image.new('RGB', (W, H), MAGENTA)
    d = ImageDraw.Draw(im)
    d.rectangle((120, 380, 280, H), fill=CARDIGAN)                       # corpo
    d.ellipse((105, 90, 295, 330), fill=(60, 40, 36))                    # cabelo
    d.ellipse((120, 110, 280, 320), fill=SKIN)                           # rosto
    for x0, x1 in ((135, 195), (205, 265)):                              # olhos
        d.ellipse((x0, 165, x1, 195), fill=(255, 255, 255), outline=(20, 20, 20), width=3)
        d.ellipse(((x0 + x1) // 2 - 9, 170, (x0 + x1) // 2 + 9, 190), fill=(110, 60, 20))
    mouth = {'neutra': [(170, 262), (230, 262)], 'feliz': [(165, 255), (200, 275), (235, 255)]}.get(expression)
    if mouth:
        d.line(mouth, fill=(150, 60, 60), width=5)
    elif expression == 'falando':
        d.ellipse((172, 245, 228, 285), fill=(70, 20, 25))                # boca aberta, larga
    elif expression == 'surpresa':
        d.ellipse((186, 245, 214, 285), fill=(70, 20, 25))                # boca em "o"
    return im


def make_asset(root: Path, name='teste', sizes=(W, H), with_eyes=True) -> Path:
    folder = root / 'personagens' / name
    folder.mkdir(parents=True)
    images = {}
    for ex in ('neutra', 'feliz', 'surpresa', 'falando'):
        draw_figure(ex).resize(sizes).save(folder / f'{ex}.png')
        images[ex] = f'{ex}.png'
    boxes = dict(BOXES)
    if not with_eyes:
        boxes.pop('eye_l'), boxes.pop('eye_r')
    man = {'name': name.title(), 'images': images, 'ref_size': [W, H], 'boxes': boxes, 'neck': [200, 335], 'tilt_fade': [320, 400]}
    (folder / 'personagem.json').write_text(json.dumps(man), encoding='utf-8')
    return folder


@pytest.fixture
def asset_dir(tmp_path):
    make_asset(tmp_path)
    return tmp_path


def changed_box(a: Image.Image, b: Image.Image):
    """Caixa (x0, y0, x1, y1) onde as duas imagens RGBA diferem de verdade (ignora ruído de 1-2 níveis)."""
    diff = np.abs(np.asarray(a.convert('RGBA')).astype(int) - np.asarray(b.convert('RGBA')).astype(int)).max(axis=2)
    ys, xs = np.where(diff > 6)
    return None if xs.size == 0 else (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


# ------------------------------------------------------------------ recorte e biblioteca

def test_recorte_por_cor_remove_o_fundo_e_mantem_o_personagem_sem_halo_magenta():
    out = cutout.key_image(draw_figure())
    a = np.asarray(out.getchannel('A'))
    assert a[5, 5] == 0 and a[5, W - 5] == 0           # cantos: fundo transparente
    assert a[250, 200] == 255 and a[500, 200] == 255   # rosto e corpo: opacos
    rgb = np.asarray(out.convert('RGB')).astype(int)
    edge = (a > 10) & (a < 245)
    if edge.any():  # nas bordas semitransparentes o magenta é atenuado (R e B não passam muito do verde)
        spill = np.minimum(rgb[..., 0], rgb[..., 2]) - rgb[..., 1]
        assert spill[edge].mean() < 120


def test_manifesto_e_biblioteca_dizem_o_que_esta_errado(tmp_path):
    folder = make_asset(tmp_path)
    man = json.loads((folder / 'personagem.json').read_text(encoding='utf-8'))
    cutout.validate_manifest(man)
    for mudar, trecho in ((lambda m: m['images'].pop('neutra'), 'neutra'), (lambda m: m.update(ref_size=[1]), 'ref_size'),
                          (lambda m: m['boxes'].pop('mouth'), 'boxes.mouth'), (lambda m: m['boxes'].update(face=[5, 5, 1, 1]), 'boxes.face')):
        ruim = json.loads(json.dumps(man))
        mudar(ruim)
        with pytest.raises(ValueError, match=trecho):
            cutout.validate_manifest(ruim)
    assert cutout.find_asset('teste', tmp_path) == folder
    with pytest.raises(FileNotFoundError, match='"nao_existe" não encontrada.*personagens/'):
        cutout.find_asset('nao_existe', tmp_path)
    with pytest.raises(ValueError, match='inválido'):
        cutout.find_asset('../fora', tmp_path)  # nome com caminho não sai da biblioteca


def test_imagens_de_tamanhos_diferentes_sao_recusadas(tmp_path):
    folder = make_asset(tmp_path)
    Image.open(folder / 'feliz.png').resize((200, 300)).save(folder / 'feliz.png')
    with pytest.raises(ValueError, match='mesmo tamanho e enquadramento'):
        cutout.CutoutAsset(folder, 300)


# ------------------------------------------------------------------ animação: cada parte mexe só no seu lugar

def test_render_tem_o_tamanho_pedido_e_o_corpo_base_nao_muda_sem_pose(asset_dir):
    a = cutout.CutoutAsset(asset_dir / 'personagens' / 'teste', 300)
    x0, y0, x1, y1 = a.crop  # a camada é recortada à silhueta (sem o fundo vazio dos lados e do topo), mantendo o pé da imagem
    assert y1 == H and x0 > 0 and y0 > 0 and (a.w, a.h) == (round((x1 - x0) * 0.75), round((H - y0) * 0.75))
    assert a.w < 300 * 0.75 * 1.0 and a.face_cy < a.h / 2
    quieto = a.render({})
    assert quieto.mode == 'RGBA' and quieto.size == (a.w, a.h)
    assert changed_box(quieto, a.render({})) is None  # determinístico


def test_boca_muda_so_a_regiao_da_boca_e_abre_aos_poucos(asset_dir):
    a = cutout.CutoutAsset(asset_dir / 'personagens' / 'teste', 400)
    base = a.render({})
    mouth = a.box['mouth']
    ab = [a.render({'mouth': m, 'mouth_w': 1.0}) for m in (0.15, 0.5, 1.0)]
    for img in ab:
        box = changed_box(base, img)
        assert box is not None and mouth[0] - 2 <= box[0] and box[2] <= mouth[2] + 2 and mouth[1] - 2 <= box[1] and box[3] <= mouth[3] + 2
    # quanto mais aberta, mais pixels diferem da boca fechada (abertura gradual, não liga/desliga)
    dif = [np.abs(np.asarray(i).astype(int) - np.asarray(base).astype(int)).sum() for i in ab]
    assert dif[0] < dif[1] < dif[2]
    assert changed_box(a.render({'mouth': 1.0, 'mouth_w': 1.0}), a.render({'mouth': 1.0, 'mouth_w': 0.55})) is not None  # "o" != "a"
    assert changed_box(base, a.render({'mouth': 0.02})) is None  # boca (quase) fechada: nada muda


def test_piscar_so_mexe_nos_olhos_e_expressao_so_no_rosto(asset_dir):
    a = cutout.CutoutAsset(asset_dir / 'personagens' / 'teste', 400)
    base = a.render({})
    blink = changed_box(base, a.render({'blink': 1.0}))
    ex0, ey0, ex1, ey1 = min(a.box['eye_l'][0], a.box['eye_r'][0]), a.box['eye_l'][1], max(a.box['eye_l'][2], a.box['eye_r'][2]), a.box['eye_l'][3]
    assert blink and ex0 - 2 <= blink[0] and blink[2] <= ex1 + 2 and ey0 - 2 <= blink[1] and blink[3] <= ey1 + 2
    assert changed_box(base, a.render({'blink': 0.02})) is None
    face = a.box['face']
    for emo, nome in (('happy', 'feliz'), ('surprised', 'surpresa')):
        box = changed_box(base, a.render({'expr': (emo, 1.0)}))
        assert box and face[0] - 2 <= box[0] and box[2] <= face[2] + 2 and face[1] - 2 <= box[1] and box[3] <= face[3] + 2, nome
    meio, cheio = a.render({'expr': ('happy', 0.5)}), a.render({'expr': ('happy', 1.0)})
    assert np.abs(np.asarray(meio).astype(int) - np.asarray(base).astype(int)).sum() < np.abs(np.asarray(cheio).astype(int) - np.asarray(base).astype(int)).sum()
    assert changed_box(base, a.render({'expr': ('thinking', 1.0)})) is None  # emoção sem imagem própria: cai na neutra


def test_sem_caixas_de_olhos_o_piscar_e_ignorado(tmp_path):
    make_asset(tmp_path, with_eyes=False)
    a = cutout.CutoutAsset(tmp_path / 'personagens' / 'teste', 300)
    assert changed_box(a.render({}), a.render({'blink': 1.0})) is None


def test_inclinar_a_cabeca_gira_a_cabeca_e_deixa_os_pes_no_lugar(asset_dir):
    a = cutout.CutoutAsset(asset_dir / 'personagens' / 'teste', 400)
    base, tilted = a.render({}), a.render({'tilt': 10.0})
    box = changed_box(base, tilted)
    assert box is not None and box[1] < a.h * 0.55            # mudou na região da cabeça
    low = (0, int(a.h * 0.80), a.w, a.h)                       # corpo baixo (longe do pescoço): praticamente intacto
    def sobre_cinza(im):  # compara o que SE VÊ (o RGB de pixels totalmente transparentes não importa)
        bg = Image.new('RGBA', im.size, (128, 128, 128, 255))
        bg.alpha_composite(im)
        return np.asarray(bg.crop(low)).astype(int)
    dif = np.abs(sobre_cinza(base) - sobre_cinza(tilted)).max(axis=2)
    assert (dif > 6).mean() < 0.01                             # no máximo uma coluna de 1 px na borda (interpolação)
    assert changed_box(tilted, a.render({'tilt': -10.0})) is not None  # os dois sentidos são diferentes
    # balanço e respiração mexem no corpo todo, de forma suave
    assert changed_box(base, a.render({'lean': 30.0, 'breath': 1.5})) is not None


# ------------------------------------------------------------------ palco, motor e compatibilidade

def test_validacao_do_campo_asset_da_ficha():
    base = {'toon': {'characters': {'ana': {'asset': 'marina'}}}, 'scenes': [{'speaker': 'ana', 'narration': 'Oi.'}]}
    engine.validate_script(base)
    for mudar, trecho in ((lambda d: d['toon']['characters']['ana'].update(asset='../x'), 'ana.*asset'),
                          (lambda d: d['toon']['characters']['ana'].update(asset=3), 'ana.*asset'),
                          (lambda d: d['toon']['characters']['ana'].update(scale=9), 'ana.*scale')):
        ruim = json.loads(json.dumps(base))
        mudar(ruim)
        with pytest.raises(StudioError, match=trecho):
            engine.validate_script(ruim)


def test_palco_com_personagem_por_recortes_gera_quadros_na_base_do_quadro(asset_dir):
    stage = toon.Stage(270, 480, {'ana': {'asset': 'teste'}}, background='soft', base_dir=asset_dir)
    assert stage.ss == 1 and 'ana' in stage.cut and stage.bg.size == (270, 480)  # sem supersampling: já tem alta resolução
    ws = [subtitles.Word(t, 0.2 + i * 0.4, 0.2 + i * 0.4 + 0.3) for i, t in enumerate('Eu não acredito nisso'.split())]
    for cam in ('wide', 'speaker', 'reaction'):
        x0, y0, x1, y1 = stage._rect(cam, 'ana', 0.5)
        assert 0 <= x0 < x1 <= 270 and 0 <= y0 < y1 <= 480
    frames = list(stage.scene_frames('ana', ws, 12, 30, emotion='surprised', camera='wide'))
    assert len(frames) == 12 and len(frames[0]) == 270 * 480 * 3 and len(set(frames)) > 5  # a personagem se mexe
    # o corpo termina na base do quadro: a última linha de pixels não é só cenário
    arr = np.frombuffer(frames[6], dtype=np.uint8).reshape(480, 270, 3)
    assert np.abs(arr[-1].astype(int) - np.asarray(stage.bg.convert('RGB'))[-1].astype(int)).max() > 40


def test_personagem_inexistente_e_misturar_com_desenhado_por_codigo(tmp_path):
    with pytest.raises(FileNotFoundError, match='não encontrada'):
        toon.Stage(120, 200, {'ana': {'asset': 'fantasma'}}, base_dir=tmp_path)
    # compatibilidade: sem "asset" nada muda (supersampling 2x e bonecos desenhados por código, como antes)
    code = toon.Stage(120, 200, {'ana': {}, 'leo': {}})
    assert code.ss == 2 and not code.cut
    # misturar os dois tipos é permitido (o desenhado por código continua funcionando ao lado de uma personagem por recortes)
    make_asset(tmp_path)
    mix = toon.Stage(120, 200, {'ana': {'asset': 'teste'}, 'leo': {}}, base_dir=tmp_path)
    assert mix.ss == 2 and set(mix.cut) == {'ana'}
    ws = [subtitles.Word('oi', 0.1, 0.4)]
    assert len(list(mix.scene_frames('leo', ws, 3, 30, camera='wide'))) == 3


def test_fundo_soft_e_um_degrade_suave():
    im = toon.draw_room(100, 200, 1, 'soft')
    assert im.size == (100, 200) and im.getpixel((50, 5)) != im.getpixel((50, 195))
    assert 'soft' in toon.BACKGROUNDS


@needs_ffmpeg
def test_video_completo_com_personagem_por_recortes_e_erro_amigavel_se_faltar(tmp_path):
    make_asset(tmp_path)
    script = {'channel': 'T', 'fps': 25, 'resolution': '360x640', 'subtitles': 'topbox', 'images': {'provider': 'none'},
              'toon': {'background': 'soft', 'characters': {'ana': {'asset': 'teste'}}},
              'scenes': [{'speaker': 'ana', 'emotion': 'surprised', 'narration': 'Eu não acredito nisso.'},
                         {'speaker': 'ana', 'emotion': 'happy', 'narration': 'Mas que bom!'}]}
    path = tmp_path / 'r.json'
    path.write_text(json.dumps(script), encoding='utf-8')
    done = subprocess.run([sys.executable, str(ROOT / 'main.py'), '--script', str(path), '--no-voice', '--preset', 'ultrafast'],
                          capture_output=True, text=True, encoding='utf-8', errors='replace')
    assert done.returncode == 0, done.stdout + done.stderr
    assert 'Cena 1 (toon)' in done.stdout and (tmp_path / 'output' / 'video_final.mp4').exists()
    script['toon']['characters']['ana']['asset'] = 'fantasma'
    path.write_text(json.dumps(script), encoding='utf-8')
    done = subprocess.run([sys.executable, str(ROOT / 'main.py'), '--script', str(path), '--no-voice'],
                          capture_output=True, text=True, encoding='utf-8', errors='replace',
                          env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    assert done.returncode != 0 and 'Personagem "fantasma" não encontrada' in done.stdout + done.stderr
    assert 'Traceback' not in done.stderr


REAL = ROOT.parent / 'canais' / 'geeklab' / 'personagens' / 'marina'


@pytest.mark.skipif(not (REAL / 'personagem.json').exists(), reason='personagem Marina não está na biblioteca')
def test_personagem_real_do_gemini_anima_sem_buracos():
    a = cutout.CutoutAsset(REAL, 600)
    base = a.render({})
    for pose in ({'mouth': 0.3, 'mouth_w': 1.0}, {'mouth': 1.0, 'mouth_w': 0.6}, {'blink': 1.0}, {'expr': ('happy', 1.0)}, {'tilt': 8.0}):
        img = a.render(pose)
        # nenhuma pose cria buraco: o miolo do rosto e do corpo continua opaco
        for x, y in ((int(a.w * 0.5), int(a.h * 0.20)), (int(a.w * 0.5), int(a.h * 0.55))):
            assert img.getpixel((x, y))[3] == 255, (pose, x, y)
        assert img.size == base.size
