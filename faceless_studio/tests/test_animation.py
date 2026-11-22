"""Animações (gráficos, legendas pop/caixa, entradas e movimentos de cena) e formato vertical."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import main as engine
from studio import chart_anim, layouts, subtitles, video, visuals
from studio.util import StudioError

ROOT = Path(__file__).resolve().parent.parent
needs_ffmpeg = pytest.mark.skipif(not (shutil.which('ffmpeg') and shutil.which('ffprobe')),
                                  reason='FFmpeg não encontrado')
TEXT = ('Quando um paciente chega à unidade de terapia intensiva, os primeiros minutos exigem organização '
        'e decisões rápidas; cardiovasculares, neurológicas e extraordinariamente respiratórias.')


def words_for(text, step=0.35):
    return [subtitles.Word(t, i * step, (i + 1) * step) for i, t in enumerate(text.split())]


def make_ctx(w=1080, h=1920, scene=None, words=None):
    fonts = {'bold': visuals.find_font(True), 'regular': visuals.find_font(False)}
    words = words if words is not None else words_for(TEXT)
    return layouts.Ctx(scene or {}, 1, w, h, 'health', 'Canal', fonts, visuals.font_family(fonts['bold']),
                       words, 0.5, words[-1].end + 0.5, words[-1].end + 1.2)


# ------------------------------------------------------------------ legendas

@pytest.mark.parametrize('w,h', [(1920, 1080), (1080, 1920), (1080, 1080)])
@pytest.mark.parametrize('mode', ['karaoke', 'simple', 'pop', 'box'])
def test_nenhum_bloco_de_legenda_estoura_a_largura(tmp_path, w, h, mode):
    """Mede os blocos que o ASS realmente contém (como o main.py gera) contra a largura útil."""
    font = visuals.find_font(True)
    m = subtitles.caption_metrics(w, h, mode)
    path = tmp_path / 'c.ass'
    subtitles.write_scene_ass(path, words_for(TEXT), None, 30, w, h, 'Arial', (103, 233, 208), mode,
                              font_path=font)
    n = 0
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.startswith('Dialogue') and ',Sub,' in line:
            raw = line.split(',', 9)[9]
            size = int((re.search(r'\\fs(\d+)', raw) or [None, m['fs']])[1])  # \fsN encolhe só este bloco
            text = re.sub(r'\{[^}]*\}', '', raw)
            assert visuals.text_width(text, font, round(size * subtitles.PIL_PER_ASS)) <= m['avail'] + 1, \
                (mode, w, h, text)
            n += 1
    assert n >= 3


def test_legenda_pop_e_caixa_geram_ass_animado(tmp_path):
    words = words_for('Isso é um teste de legenda animada, com várias palavras.')
    for mode, border in (('pop', ',0,0,1,'), ('box', ',0,0,3,')):
        path = tmp_path / f'{mode}.ass'
        subtitles.write_scene_ass(path, words, None, 6, 1080, 1920, 'Arial', (103, 233, 208), mode)
        ass = path.read_text(encoding='utf-8')
        assert subtitles.POP_TAGS in ass and 'ISSO' in ass  # entra "saltando" e em maiúsculas
        assert border in re.search(r'Style: Sub,.*', ass).group(0)  # contorno (pop) ou caixa opaca (box)
    with pytest.raises(ValueError):
        subtitles.write_scene_ass(tmp_path / 'x.ass', words, None, 6, 1080, 1920, 'Arial', (1, 2, 3), 'nope')


def test_legenda_vertical_fica_acima_da_faixa_do_shorts():
    v, h = subtitles.caption_metrics(1080, 1920, 'pop'), subtitles.caption_metrics(1920, 1080, 'karaoke')
    assert v['margin_v'] >= 0.2 * 1920 and h['margin_v'] < 0.1 * 1080


# ------------------------------------------------------------------ validação, entradas e movimentos

@pytest.mark.parametrize('data, trecho', [
    ({'scenes': [{'narration': 'x', 'transition': 'wipe'}]}, 'transition'),
    ({'default_transition': 'wipe', 'scenes': [{'narration': 'x'}]}, 'default_transition'),
    ({'subtitles': 'neon', 'scenes': [{'narration': 'x'}]}, 'subtitles'),
    ({'resolution': '1080-1920', 'scenes': [{'narration': 'x'}]}, 'resolution'),
    ({'scenes': [{'narration': 'x', 'motion': 'spin'}]}, 'motion'),
])
def test_validate_script_recusa_valores_novos_invalidos(data, trecho):
    with pytest.raises(StudioError, match=trecho):
        engine.validate_script(data)


def test_validate_script_aceita_entradas_movimentos_e_legendas_novos():
    engine.validate_script({'resolution': '1080x1920', 'subtitles': 'box', 'default_transition': 'punch',
                            'scenes': [{'narration': 'x', 'transition': t, 'motion': m}
                                       for t in video.ENTRIES for m in video.MOTIONS]})


def test_entrada_da_cena_usa_o_padrao_do_roteiro():
    assert engine.entry_of({}, {'default_transition': 'punch'}) == 'punch'
    assert engine.entry_of({'transition': 'flash'}, {'default_transition': 'punch'}) == 'flash'
    assert engine.entry_of({}, {}) == 'cut'


def test_movimentos_novos_e_punch():
    for m in ('pan_up', 'pan_down', 'shake', 'static', 'zoom_in'):
        z, x, y = video.motion_exprs(m, 90, 0.08, punch_frames=9)
        assert 'pow(max(0,1-on/9),2)' in z, m
    z, x, y = video.motion_exprs('pan_up', 90, 0.08)
    assert 'on' not in z and 'on/89' in y
    assert video.motion_exprs('static', 90, 0.08) == ('1', '0', '0')  # sem punch: igual ao de antes
    assert video.pick_motion('auto', 2, 'image', portrait=True) == 'pan_up'
    assert video.pick_motion('auto', 2, 'image') == 'pan_right'
    assert video.pick_motion('shake', 1, 'image') == 'shake'


# ------------------------------------------------------------------ gráficos animados (ASS)

def events(evs, style):
    out = []
    for line in evs:
        f = line.split(',', 9)
        if f[3] == style:
            out.append((f[1], f[2], f[9]))
    return out


def cs(t):  # h:mm:ss.cc -> centésimos
    h, m, s = t.split(':')
    sec, c = s.split('.')
    return ((int(h) * 60 + int(m)) * 60 + int(sec)) * 100 + int(c)


def test_grafico_de_barras_anima_e_os_valores_nao_se_sobrepoem():
    c = make_ctx(1920, 1080)
    spec = {'type': 'bar', 'labels': ['Alfa', 'Beta', 'Gama'], 'values': [40, 25, 10], 'unit': '%'}
    styles, evs = chart_anim.build(c, spec, 0.3, 0.78)
    assert any('CBar' in s for s in styles)
    bars = [e for e in events(evs, 'CBar') if '\\clip(' in e[2] and '\\t(' in e[2]]
    assert len(bars) == 3  # uma por barra, crescendo por \clip animado
    # sem "on_words": entram em sequência
    assert [cs(b[0]) for b in bars] == sorted(cs(b[0]) for b in bars)
    # a contagem do valor: eventos consecutivos não podem se sobrepor (senão os números se misturam)
    vals = sorted(events(evs, 'CVal'), key=lambda e: cs(e[0]))
    per_bar = {}
    for a, b, text in vals:
        per_bar.setdefault(re.search(r'\\pos\((\d+),', text).group(1), []).append((cs(a), cs(b)))
    for spans in per_bar.values():
        for (a1, b1), (a2, b2) in zip(spans, spans[1:]):
            assert b1 <= a2 + 1, spans
    assert any('40%' in e[2] for e in vals) and any('25%' in e[2] for e in vals)


def test_on_words_ausente_na_narracao_entra_depois_da_barra_anterior():
    c = make_ctx(1920, 1080, words=words_for('causas respiratórias e cardiovasculares'))
    spec = {'type': 'bar', 'labels': ['Resp', 'Card', 'Outras'], 'values': [3, 2, 1],
            'on_words': ['respiratórias', 'cardiovasculares', 'outras']}  # "outras" não é dita
    _, evs = chart_anim.build(c, spec, 0.3, 0.78)
    starts = [cs(b[0]) for b in events(evs, 'CBar') if '\\t(' in b[2]]
    assert starts == sorted(starts) and starts[0] == cs('0:00:00.35') or starts[0] >= 35
    assert starts[2] > starts[1]  # nunca antes da anterior


def test_rotulos_longos_no_vertical_viram_barras_horizontais():
    c = make_ctx(1080, 1920)
    spec = {'type': 'bar', 'labels': ['Respiratória', 'Cardiovascular', 'Neurológica', 'Outras'],
            'values': [42, 28, 18, 12]}
    _, evs = chart_anim.build(c, spec, 0.3, 0.66)
    labels = events(evs, 'CLabR')  # rótulos alinhados à direita = barras horizontais
    assert len(labels) == 4
    c2 = make_ctx(1920, 1080)
    _, evs2 = chart_anim.build(c2, spec, 0.3, 0.78)
    assert events(evs2, 'CLabR') == [] and len(events(evs2, 'CLab')) == 4  # no 16:9 continuam verticais


def test_grafico_de_linha_desenha_e_marca_os_pontos():
    c = make_ctx(1080, 1920)
    spec = {'type': 'line', 'labels': list('ABCDEF'), 'series': [{'name': 'x', 'values': [52, 58, 66, 71, 79, 84]}],
            'unit': '%'}
    _, evs = chart_anim.build(c, spec, 0.3, 0.66)
    line = [e for e in events(evs, 'CBar') if '\\3c' in e[2] and '\\t(' in e[2]]
    assert len(line) == 1 and '\\bord' in line[0][2]
    dots = [e for e in events(evs, 'CBar') if '\\fscx10' in e[2]]
    assert len(dots) == 6
    assert [cs(d[0]) for d in dots] == sorted(cs(d[0]) for d in dots)  # cada ponto salta quando a linha chega


def test_ticks_redondos():
    assert chart_anim._nice_ticks(44, 92) == [60, 80]
    assert chart_anim._nice_ticks(0, 1) == [0, 0.25, 0.5, 0.75, 1] or chart_anim._nice_ticks(0, 1)[0] == 0


def test_supports_e_animate_false():
    assert chart_anim.supports({'type': 'bar'}) and chart_anim.supports({'type': 'line', 'series': [{}, {}]})
    assert not chart_anim.supports({'type': 'bar', 'series': [{}, {}]})  # barras agrupadas: versão estática
    assert not chart_anim.supports({'type': 'bar', 'animate': False})
    with pytest.raises(StudioError):
        chart_anim.build(make_ctx(), {'type': 'bar', 'labels': ['a'], 'values': [1, 2]}, 0.3, 0.7)


def test_contagem_do_numero_nao_sobrepoe_eventos(tmp_path):
    c = make_ctx(1080, 1920, scene={'headline': 'X', 'number': {'value': 1240, 'label': 'atendimentos'}})
    _, evs = layouts.layout_number(c, tmp_path / 'bg.png')
    spans = sorted((cs(a), cs(b)) for a, b, _ in events(evs, 'LBig'))
    assert len(spans) > 10
    for (a1, b1), (a2, b2) in zip(spans, spans[1:]):
        assert b1 <= a2 + 1, (a1, b1, a2, b2)


# ------------------------------------------------------------------ renderização real

def ffprobe_duration(path):
    return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of',
                                 'default=nw=1:nk=1', str(path)], capture_output=True, text=True,
                                check=True).stdout)


def frame_stats(path, t, w=108, h=192, band=(0.0, 1.0)):
    """(brilho médio 0-255, nº de pixels na cor de destaque) do quadro em t segundos, só na faixa
    vertical `band` (frações da altura)."""
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{t:.3f}', '-i', str(path), '-frames:v', '1', '-vf',
                          f'scale={w}:{h}', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                         capture_output=True, check=True).stdout
    px = [raw[i:i + 3] for i in range(0, len(raw), 3)]
    px = px[int(band[0] * h) * w:int(band[1] * h) * w]
    bright = sum(sum(p) for p in px) / (3 * len(px))
    accent = sum(1 for p in px if p[0] < 160 and p[1] > 190 and p[2] > 160)  # menta (103,233,208)
    return bright, accent


@needs_ffmpeg
def test_video_vertical_com_graficos_legenda_e_entradas_animados(tmp_path):
    long_text = ' '.join(['causas respiratórias cardiovasculares neurológicas'] * 4)  # ~10 s mudos
    script = {
        'channel': 'Teste', 'theme': 'health', 'fps': 25, 'resolution': '540x960', 'subtitles': 'box',
        'default_transition': 'punch', 'images': {'provider': 'none'},
        'scenes': [
            {'title': 'Barras', 'headline': 'CAUSAS', 'narration': long_text, 'motion': 'shake',
             'chart': {'type': 'bar', 'labels': ['Respiratória', 'Cardiovascular', 'Neurológica'],
                       'values': [42, 28, 18], 'unit': '%', 'source': 'Fonte de teste bem longa para quebrar linha'}},
            {'title': 'Flash', 'headline': 'LINHA', 'transition': 'flash', 'narration': long_text,
             'chart': {'type': 'line', 'labels': ['Jan', 'Fev', 'Mar', 'Abr'],
                       'series': [{'name': 'a', 'values': [10, 20, 30, 40]}]}},
            {'title': 'Número', 'headline': 'TOTAL', 'transition': 'fade', 'narration': 'Mil duzentos e quarenta.',
             'number': {'value': 1240, 'label': 'atendimentos no mês'}},
        ],
    }
    path = tmp_path / 'roteiro.json'
    path.write_text(json.dumps(script), encoding='utf-8')
    done = subprocess.run([sys.executable, str(ROOT / 'main.py'), '--script', str(path), '--no-voice', '--preset',
                           'ultrafast'], capture_output=True, text=True, encoding='utf-8', errors='replace')
    assert done.returncode == 0, done.stdout + done.stderr
    final = tmp_path / 'output' / 'video_final.mp4'
    size = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                           'stream=width,height', '-of', 'csv=p=0', str(final)], capture_output=True, text=True,
                          check=True).stdout.strip()
    assert size == '540,960'

    # as barras CRESCEM: perto do início quase não há cor de destaque; depois há bastante
    start2 = ffprobe_duration(tmp_path / 'temp' / 'video_01.mp4')  # a cena 1 termina aqui
    chart_band = (0.36, 0.62)
    early = frame_stats(final, 0.6, band=chart_band)[1]   # antes de a 1ª barra entrar
    late = frame_stats(final, start2 - 0.5, band=chart_band)[1]
    assert late > early + 150, (early, late)

    # a cena 2 abre com um clarão branco (flash): o 1º quadro é bem mais claro que 1 s depois
    assert frame_stats(final, start2 + 0.04)[0] > frame_stats(final, start2 + 1.0)[0] + 25

    # legenda em caixa e entrada "pop" estão no ASS da cena 1
    ass = (tmp_path / 'temp' / 'legendas_01.ass').read_text(encoding='utf-8')
    assert subtitles.POP_TAGS in ass and 'RESPIRAT' in ass  # em maiúsculas (o roteiro está em minúsculas)
    assert ',0,0,3,' in re.search(r'Style: Sub,.*', ass).group(0)  # caixa opaca


def test_resolucao_de_rascunho_mantem_o_formato():
    assert engine.draft_resolution('1920x1080') == '1280x720'
    assert engine.draft_resolution('1080x1920') == '720x1280'
    assert engine.draft_resolution('1080x1080') == '720x720'
    assert engine.draft_resolution('3840x2160') == '1280x720'
