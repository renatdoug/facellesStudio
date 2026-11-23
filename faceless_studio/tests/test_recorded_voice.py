"""Voz gravada (campo "audio"): alinhamento local, relatório de confiança, preparo do áudio e integração com o motor.
Nenhum teste aqui precisa de internet nem do modelo de reconhecimento (o reconhecedor é substituído por um falso);
o teste com o reconhecedor de verdade só roda se `FACELESS_TEST_WHISPER=1` e o faster-whisper estiverem disponíveis."""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import main as engine
from studio import align, subtitles, voice
from studio.util import StudioError, media_duration

ROOT = Path(__file__).resolve().parent.parent
needs_ffmpeg = pytest.mark.skipif(not (shutil.which('ffmpeg') and shutil.which('ffprobe')), reason='FFmpeg não encontrado')

TEXT = 'Eu vi um ninja correndo sobre a água.'
EVENTS = [[1.0, 1.2, 'Eu'], [1.25, 1.45, 'vi'], [1.5, 1.65, 'um'], [1.7, 2.1, 'ninja'], [2.15, 2.7, 'correndo'],
          [2.75, 3.1, 'sobre'], [3.12, 3.2, 'a'], [3.25, 3.7, 'água']]


def make_audio(path, lead=1.0, tone=2.6, tail=0.8, freq=220):
    """Áudio de teste (tom) com silêncio antes e depois, como uma gravação de verdade."""
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'lavfi', '-i', f'sine=frequency={freq}:duration={tone}',
                    '-af', f'adelay={int(lead * 1000)}|{int(lead * 1000)},apad=pad_dur={tail}', '-ar', '44100', str(path)], check=True)
    return path


# ------------------------------------------------------------------ cobertura e relatório de confiança

def test_cobertura_conta_so_as_palavras_do_roteiro_ouvidas_e_diz_quais_faltaram():
    cov, missing = subtitles.match_coverage(TEXT, EVENTS)
    assert cov == 1.0 and missing == []
    cov, missing = subtitles.match_coverage(TEXT, EVENTS[:4])  # só ouviu o começo
    assert cov == pytest.approx(4 / 8) and missing == ['correndo', 'sobre', 'a', 'água.']
    assert subtitles.match_coverage('', EVENTS) == (1.0, [])
    # acentos e pontuação não atrapalham (o reconhecedor devolve "agua" sem acento, por exemplo)
    ev = [[0, 0.3, 'Agua,'], [0.4, 0.8, 'ninja']]
    assert subtitles.match_coverage('Água ninja!', ev)[0] == 1.0


def test_relatorio_ok_aviso_e_erro_conforme_a_correspondencia():
    ok = align.assess(TEXT, EVENTS, [0.9] * 8, 'whisper:small')
    assert ok.level == 'ok' and ok.coverage == 1.0 and 'alinhamento OK' in ok.summary()
    aviso = align.assess(TEXT, EVENTS[:7], [0.9] * 7, 'whisper:small')  # 7 de 8 = 87%: ok; tira mais uma
    assert aviso.level == 'ok'
    aviso = align.assess(TEXT, EVENTS[:6], [0.9] * 6, 'whisper:small')  # 6 de 8 = 75%
    assert aviso.level == 'aviso' and 'APROXIMADO' in aviso.summary() and 'água' in ' '.join(aviso.messages) and '..' not in ' '.join(aviso.messages)
    erro = align.assess(TEXT, EVENTS[:3], [0.9] * 3, 'whisper:small')  # 3 de 8 = 37%
    assert erro.level == 'erro' and 'NÃO CONFIÁVEL' in erro.summary() and erro.messages
    vazio = align.assess(TEXT, [], [], 'whisper:small')
    assert vazio.level == 'erro' and 'Nenhuma fala' in vazio.messages[0]


def test_relatorio_pega_baixa_confianca_ritmo_impossivel_e_tempos_alem_do_audio():
    baixa = align.assess(TEXT, EVENTS, [0.2] * 8, 'whisper:small')
    assert baixa.level == 'aviso' and 'confiança' in baixa.messages[0]
    lento = [[i * 5.0, i * 5.0 + 0.3, w] for i, w in enumerate(TEXT.split())]  # 8 palavras em 35 s
    assert align.assess(TEXT, lento, None, 'manual').level == 'aviso'
    alem = align.assess(TEXT, EVENTS, None, 'manual', audio_seconds=2.0)  # tempos passam do fim do áudio
    assert alem.level == 'erro' and 'passam do fim' in ' '.join(alem.messages)
    assert align.assess(TEXT, EVENTS, None, 'manual').mean_prob is None  # manual: sem "confiança" inventada


# ------------------------------------------------------------------ origem dos tempos (manual, cache, reconhecedor)

def test_tempos_manuais_ao_lado_do_audio_tem_prioridade_e_sao_validados(tmp_path):
    audio = tmp_path / 'fala.wav'
    audio.write_bytes(b'x')
    side = tmp_path / 'fala.palavras.json'
    side.write_text(json.dumps(EVENTS), encoding='utf-8')
    ev, probs, source = align.word_events(audio, tmp_path, transcribe=lambda *a: pytest.fail('não devia reconhecer'))
    assert source == 'manual' and probs is None and ev == EVENTS
    for ruim, trecho in (('{"a": 1}', 'inválidos'), ('[[1, 0.5, "x"]]', 'inválidos'), ('[[2, 3, "b"], [1, 1.5, "a"]]', 'fora de ordem'),
                         ('isto não é json', 'JSON válido')):
        side.write_text(ruim, encoding='utf-8')
        with pytest.raises(StudioError, match=trecho):
            align.word_events(audio, tmp_path)


def test_reconhecimento_roda_uma_vez_e_fica_em_cache(tmp_path):
    audio = tmp_path / 'fala.wav'
    audio.write_bytes(b'conteudo da gravacao')
    chamadas = []

    def falso(path, model):
        chamadas.append(model)
        return EVENTS, [0.9] * len(EVENTS)
    a = align.word_events(audio, tmp_path, 'small', transcribe=falso)
    b = align.word_events(audio, tmp_path, 'small', transcribe=falso)
    assert a == b and chamadas == ['small'] and a[2] == 'whisper:small'
    audio.write_bytes(b'outra gravacao')  # outro conteúdo = outra chave de cache
    align.word_events(audio, tmp_path, 'small', transcribe=falso)
    align.word_events(audio, tmp_path, 'base', transcribe=falso)  # outro modelo também
    assert len(chamadas) == 3


def test_sem_o_alinhador_instalado_a_mensagem_diz_o_que_fazer(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, 'faster_whisper', None)  # como se não estivesse instalado
    align._load_model.cache_clear()
    with pytest.raises(StudioError, match='requirements-voz.txt.*palavras.json'):
        align._load_model('small')


# ------------------------------------------------------------------ preparo do áudio gravado

@needs_ffmpeg
def test_gravacao_perde_o_silencio_do_comeco_e_os_tempos_andam_junto(tmp_path):
    audio = make_audio(tmp_path / 'fala.wav', lead=1.0, tone=2.7, tail=0.8)
    (tmp_path / 'fala.palavras.json').write_text(json.dumps(EVENTS), encoding='utf-8')
    wav, events, probs, source = voice.recorded(audio, tmp_path)
    cut = 1.0 - voice.LEAD_PAD
    assert source == 'manual' and probs is None
    assert events[0][0] == pytest.approx(voice.LEAD_PAD) and events[-1][1] == pytest.approx(3.7 - cut)
    assert [e[2] for e in events] == [e[2] for e in EVENTS]
    assert media_duration(wav) == pytest.approx(media_duration(audio) - cut, abs=0.08)  # cortou só o começo
    assert wav.exists() and voice.recorded(audio, tmp_path)[0] == wav                    # cache reaproveitado
    # o fim da fala é medido como nas outras vozes (silêncio final cortado, com folga)
    speech = voice.speech_seconds(wav, events, media_duration(wav))
    assert 3.7 - cut <= speech <= media_duration(wav)


@needs_ffmpeg
def test_gravacao_baixa_e_altas_ficam_com_volume_parecido(tmp_path):
    def mean_volume(path):
        p = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', str(path), '-af', 'volumedetect', '-f', 'null', '-'],
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        return float(re.search(r'mean_volume: (-?[\d.]+) dB', p.stderr).group(1))
    saidas = []
    for nome, ganho in (('baixa', 0.05), ('alta', 0.9)):
        raw = tmp_path / f'{nome}.wav'
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'lavfi', '-i', 'sine=frequency=220:duration=3', '-af',
                        f'volume={ganho},adelay=500|500', str(raw)], check=True)
        (tmp_path / f'{nome}.palavras.json').write_text(json.dumps([[0.5, 3.4, 'fala']]), encoding='utf-8')
        saidas.append(mean_volume(voice.recorded(raw, tmp_path)[0]))
    assert abs(saidas[0] - saidas[1]) < 4.0, saidas


def test_roteiro_de_gravacao_lista_so_as_falas_do_personagem():
    cenas = [{'id': 'gancho', 'speaker': 'ana', 'narration': 'Oi.'}, {'id': 'a b', 'speaker': 'teo', 'narration': ' Olá! '},
             {'speaker': 'teo', 'narration': 'Tchau.'}]
    assert align.recording_sheet(cenas, 'teo') == [(2, 'a_b', 'teo_02_a_b.wav', 'Olá!'), (3, 'cena3', 'teo_03_cena3.wav', 'Tchau.')]
    assert align.recording_sheet(cenas, 'zeca') == []


# ------------------------------------------------------------------ integração com o motor

def run_engine(script, *extra):
    return subprocess.run([sys.executable, str(ROOT / 'main.py'), '--script', str(script), '--preset', 'ultrafast', *extra],
                          capture_output=True, text=True, encoding='utf-8', errors='replace',
                          env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})


def cartao(audio='fala.wav', narration=TEXT):
    return {'channel': 'T', 'fps': 25, 'resolution': '360x640', 'images': {'provider': 'none'},
            'scenes': [{'headline': 'TESTE', 'narration': narration, 'audio': audio}]}


@needs_ffmpeg
def test_cena_com_audio_gravado_usa_os_tempos_do_alinhador_nas_legendas(tmp_path):
    make_audio(tmp_path / 'fala.wav', lead=1.0, tone=2.7, tail=0.8)
    (tmp_path / 'fala.palavras.json').write_text(json.dumps(EVENTS), encoding='utf-8')
    script = tmp_path / 'r.json'
    script.write_text(json.dumps(cartao()), encoding='utf-8')
    done = run_engine(script)
    assert done.returncode == 0, done.stdout + done.stderr
    assert 'voz gravada "fala.wav"' in done.stdout and 'alinhamento OK' in done.stdout and 'tempos: manual' in done.stdout
    srt = (tmp_path / 'output' / 'video_final.srt').read_text(encoding='utf-8')
    h, m, s = re.search(r'(\d\d):(\d\d):(\d\d,\d+) -->', srt).groups()
    first = int(h) * 3600 + int(m) * 60 + float(s.replace(',', '.'))
    # 1ª palavra falada em 1,0 s no arquivo; o motor cortou 0,88 s do começo; a cena entra com fade (head)
    assert first == pytest.approx(engine.FADE + 0.1 + voice.LEAD_PAD, abs=0.02), first
    assert media_duration(tmp_path / 'output' / 'video_final.mp4') > 3.0
    # as cenas SEM "audio" continuam usando o caminho de antes (voz sintética): o campo é opcional
    outra = cartao()
    outra['scenes'][0].pop('audio')
    script.write_text(json.dumps(outra), encoding='utf-8')
    assert 'voz gravada' not in run_engine(script, '--no-voice').stdout


@needs_ffmpeg
def test_alinhamento_sem_confianca_para_antes_de_renderizar(tmp_path):
    make_audio(tmp_path / 'fala.wav')
    (tmp_path / 'fala.palavras.json').write_text(json.dumps([[1.0, 1.3, 'banana'], [1.4, 1.9, 'maçã']]), encoding='utf-8')
    script = tmp_path / 'r.json'
    script.write_text(json.dumps(cartao()), encoding='utf-8')
    done = run_engine(script)
    out = done.stdout + done.stderr
    assert done.returncode != 0 and 'não é confiável' in out and 'Cena 1' in out and 'nada foi renderizado' in out
    assert 'NÃO CONFIÁVEL' in out and 'Traceback' not in done.stderr
    assert not (tmp_path / 'output' / 'video_final.mp4').exists()


@needs_ffmpeg
def test_audio_inexistente_ou_invalido_vira_erro_claro(tmp_path):
    script = tmp_path / 'r.json'
    script.write_text(json.dumps(cartao(audio='nao_existe.wav')), encoding='utf-8')
    done = run_engine(script)
    assert done.returncode != 0 and 'Áudio da cena 1 não encontrado' in done.stdout + done.stderr
    bad = cartao()
    bad['scenes'][0]['audio'] = 3
    with pytest.raises(StudioError, match='Cena 1.*audio'):
        engine.validate_script(bad)
    engine.validate_script(cartao())  # compatível: roteiro com o campo novo é válido


@needs_ffmpeg
def test_roteiro_de_gravacao_pela_linha_de_comando(tmp_path):
    script = tmp_path / 'r.json'
    script.write_text(json.dumps({'channel': 'T', 'toon': {'characters': {'teo': {}, 'ana': {}}},
                                  'scenes': [{'id': 'a', 'speaker': 'ana', 'narration': 'Oi!'},
                                             {'id': 'b', 'speaker': 'teo', 'narration': 'Olá, tudo bem?'}]}), encoding='utf-8')
    done = run_engine(script, '--recording-sheet', 'teo')
    assert done.returncode == 0, done.stdout + done.stderr
    assert 'teo_02_b.wav' in done.stdout and 'Olá, tudo bem?' in done.stdout and 'Oi!' not in done.stdout
    assert (tmp_path / 'gravacao_teo.txt').read_text(encoding='utf-8').startswith('Falas de teo')
    assert run_engine(script, '--recording-sheet', 'zeca').returncode != 0


# ------------------------------------------------------------------ reconhecedor de verdade (opcional, precisa do modelo)

@pytest.mark.skipif(os.environ.get('FACELESS_TEST_WHISPER') != '1', reason='defina FACELESS_TEST_WHISPER=1 (baixa o modelo)')
def test_reconhecedor_local_acha_as_palavras_em_portugues(tmp_path):
    pytest.importorskip('faster_whisper')
    mp3, ref = voice.synthesize(TEXT, 'pt-BR-AntonioNeural', '+0%', tmp_path)  # precisa de internet (edge-tts)
    events, probs = align.transcribe_words(mp3, 'small')
    rep = align.assess(TEXT, events, probs, 'whisper:small', media_duration(mp3))
    assert rep.level in ('ok', 'aviso') and rep.coverage >= 0.85
    # os tempos reais do edge-tts são a verdade de referência: a 1ª palavra deve cair a menos de 0,3 s
    assert abs(events[0][0] - ref[0][0]) < 0.3


def test_voz_gravada_tolera_nomes_proprios_e_homofonos_mas_nao_texto_diferente():
    ouvido = [[0.0, 0.3, 'Sem,'], [0.4, 0.6, 'nem'], [0.7, 0.8, 'o'], [0.9, 1.1, 'use'], [1.1, 1.2, 'em'], [1.3, 1.5, 'bot'],
              [1.6, 1.9, 'corre'], [2.0, 2.3, 'tanto.']]
    texto = 'Cem? Nem o Usain Bolt corre tanto!'
    assert subtitles.match_coverage(texto, ouvido)[0] < 0.7               # casamento exato (edge-tts): não casa
    assert subtitles.match_coverage(texto, ouvido, fuzzy=True)[0] == 1.0  # voz gravada: casa
    assert align.assess(texto, ouvido, [0.7] * 8, 'whisper:small').level == 'ok'
    # a tolerância não vira "aceita tudo": outro texto continua sendo recusado
    outro = [[0.0, 0.5, 'banana'], [0.6, 1.0, 'maçã'], [1.1, 1.5, 'laranja'], [1.6, 2.0, 'uva']]
    assert align.assess(texto, outro, [0.9] * 4, 'whisper:small').level == 'erro'
    # os tempos de cada palavra do roteiro vêm da palavra parecida
    ws = subtitles.align_words(texto, ouvido, 2.5, fuzzy=True)
    assert ws[0].start == 0.0 and ws[3].start == pytest.approx(0.9) and ws[4].start == pytest.approx(1.3)


def test_bordas_das_palavras_acompanham_a_energia_da_voz():
    """O reconhecedor estica a 1ª palavra para dentro do silêncio antes da fala; o ajuste a leva até a voz de verdade."""
    np = pytest.importorskip('numpy')
    sr = 16000

    def tom(seg):
        t = np.arange(int(seg * sr)) / sr
        return (0.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    mudo = lambda seg: np.zeros(int(seg * sr), dtype=np.float32)  # noqa: E731
    ruido = np.random.default_rng(1).normal(0, 0.002, int(3.0 * sr)).astype(np.float32)
    voz = np.concatenate([mudo(1.0), tom(0.8), mudo(0.3), tom(0.5), mudo(0.4)]) + ruido[:int(3.0 * sr)]
    # voz real: 1,0-1,8 e 2,1-2,6. O reconhecedor marcou a 1ª palavra de 0,56 a 1,8 e a 2ª já bem posicionada
    esticado = [[0.56, 1.8, 'Na'], [2.1, 2.6, 'vida']]
    refinado = align.refine_boundaries(esticado, voz, sr)
    assert refinado[0][0] == pytest.approx(1.0, abs=0.03) and refinado[0][1] == pytest.approx(1.8, abs=0.04)
    assert refinado[1][0] == pytest.approx(2.1, abs=0.02) and refinado[1][1] == pytest.approx(2.6, abs=0.04)  # não mexe no que já está bom
    # fim esticado para o silêncio depois da palavra também volta
    assert align.refine_boundaries([[1.0, 2.0, 'x']], voz, sr)[0][1] == pytest.approx(1.8, abs=0.04)
    # sem contraste (áudio todo mudo): devolve como veio, sem inventar nada
    assert align.refine_boundaries(esticado, np.zeros(sr * 3, dtype=np.float32), sr) == esticado
    assert align.refine_boundaries([], voz, sr) == []


# ------------------------------------------------------------------ aviso visível de alinhamento aproximado + gravações fora do Git

@needs_ffmpeg
def test_alinhamento_aproximado_aparece_em_destaque_e_no_relatorio_ao_lado_do_video(tmp_path):
    make_audio(tmp_path / 'fala.wav', lead=1.0, tone=2.7, tail=0.8)
    (tmp_path / 'fala.palavras.json').write_text(json.dumps(EVENTS[:6]), encoding='utf-8')  # ouviu 6 de 8 palavras = 75%
    script = tmp_path / 'r.json'
    script.write_text(json.dumps(cartao()), encoding='utf-8')
    done = run_engine(script)
    assert done.returncode == 0, done.stdout + done.stderr  # aproximado ainda renderiza...
    assert 'CONFERIR ANTES DE PUBLICAR' in done.stdout and 'Cena 1' in done.stdout and 'água' in done.stdout  # ...mas em destaque
    rel = (tmp_path / 'output' / 'video_final_alinhamento.txt').read_text(encoding='utf-8')
    assert rel.startswith('Alinhamento da voz gravada') and 'CONFERIR ANTES DE PUBLICAR: cenas 1' in rel
    assert re.search(r'Cena 1 \(0\.0s a [\d.]+s\): ALINHAMENTO APROXIMADO', rel) and 'água' in rel


@needs_ffmpeg
def test_alinhamento_bom_gera_relatorio_sem_alarme(tmp_path):
    make_audio(tmp_path / 'fala.wav', lead=1.0, tone=2.7, tail=0.8)
    (tmp_path / 'fala.palavras.json').write_text(json.dumps(EVENTS), encoding='utf-8')
    script = tmp_path / 'r.json'
    script.write_text(json.dumps(cartao()), encoding='utf-8')
    done = run_engine(script)
    assert done.returncode == 0, done.stdout + done.stderr
    assert 'CONFERIR' not in done.stdout and 'alinhamento OK em todas as cenas' in done.stdout
    rel = (tmp_path / 'output' / 'video_final_alinhamento.txt').read_text(encoding='utf-8')
    assert 'Todas as cenas gravadas com alinhamento OK' in rel and 'CONFERIR' not in rel
    # sem voz gravada no roteiro não nasce relatório nenhum (projetos antigos ficam como estavam)
    antigo = cartao()
    antigo['scenes'][0].pop('audio')
    script.write_text(json.dumps(antigo), encoding='utf-8')
    (tmp_path / 'output' / 'video_final_alinhamento.txt').unlink()
    run_engine(script, '--no-voice')
    assert not (tmp_path / 'output' / 'video_final_alinhamento.txt').exists()


@pytest.mark.skipif(not shutil.which('git'), reason='git não encontrado')
def test_gravacoes_pessoais_ficam_fora_do_git_e_audio_de_teste_sintetico_nao():
    repo = ROOT.parent
    if not (repo / '.git').exists():
        pytest.skip('não está dentro do repositório')

    def ignorado(rel):
        return subprocess.run(['git', 'check-ignore', '-q', rel], cwd=repo).returncode == 0
    for pessoal in ('canais/x/audio/teo_02_alerta.wav', 'canais/x/audio/teo_02_alerta.palavras.json', 'canais/x/audio_gravado_1/a.m4a',
                    'canais/x/minha_voz.mp3', 'canais/x/gravacao.wav'):
        assert ignorado(pessoal), pessoal
    for versionavel in ('canais/x/audio_ensaio/teo_02_alerta.wav', 'canais/x/roteiro.json', 'canais/x/gravacao_teo.txt'):
        assert not ignorado(versionavel), versionavel
