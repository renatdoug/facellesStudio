import json
import sys
import textwrap
import time

import pytest
from fastapi.testclient import TestClient

from webui.app import create_app
from webui.jobs import JobError, build_command

SCRIPT = {
    'channel': 'Teste',
    'scenes': [
        {'id': 'abertura', 'title': 'Abertura', 'narration': 'Olá mundo.', 'prompt': 'uma sala'},
        {'id': 'lista', 'title': 'Lista', 'narration': 'Itens.', 'items': [{'key': 'A', 'text': 'x'}]},
    ],
}

FAKE_MAIN = textwrap.dedent('''\
    import sys, time
    if "--fail" in sys.argv: sys.exit(3)
    print("Imagens por IA: 2 cena(s), fornecedor \\"pollinations\\"", flush=True)
    print("  cena 1: gerada (1 s) -> a.jpg", flush=True)
    print("[1/2] Cena 1 (image): Abertura", flush=True)
    print("[2/2] Cena 2 (list): Lista", flush=True)
    print("Folha de revisão", flush=True)
    if "--slow" in sys.argv: time.sleep(30)
''')


@pytest.fixture
def env(tmp_path):
    channels = tmp_path / 'canais'
    (channels / 'meu-canal' / 'assets' / 'generated').mkdir(parents=True)
    (channels / 'meu-canal' / 'output').mkdir()
    (channels / 'meu-canal' / 'roteiro.json').write_text(json.dumps(SCRIPT), encoding='utf-8')
    install = tmp_path / 'install'
    install.mkdir()
    (install / 'main.py').write_text(FAKE_MAIN, encoding='utf-8')
    client = TestClient(create_app(channels, install), base_url='http://localhost')
    return client, channels


def test_host_externo_e_origem_estranha_sao_bloqueados(env):
    client, _ = env
    assert client.get('/api/channels', headers={'host': 'evil.example'}).status_code == 403
    r = client.put('/api/channels/meu-canal/scripts/roteiro.json', json=SCRIPT,
                   headers={'origin': 'http://evil.example'})
    assert r.status_code == 403
    assert client.get('/api/channels').status_code == 200


def test_lista_canais_e_estado_da_cena(env):
    client, channels = env
    assert client.get('/api/channels').json() == [{'name': 'meu-canal', 'scripts': ['roteiro.json']}]
    gen = channels / 'meu-canal' / 'assets' / 'generated'
    (gen / 'cena_abertura_x.jpg').write_bytes(b'\xff\xd8jpg')
    (gen / 'manifest.json').write_text(json.dumps(
        {'abertura': {'file': 'cena_abertura_x.jpg', 'prompt': 'uma sala', 'provider': 'gemini'}}))
    state = client.get('/api/channels/meu-canal/scripts/roteiro.json').json()
    first, second = state['scenes']
    assert first['layout'] == 'image' and first['image']['stale'] is False
    assert first['image']['url'].endswith('/image/cena_abertura_x.jpg')
    assert second['layout'] == 'list' and second['image'] is None
    # prompt editado depois da geração => imagem desatualizada
    SCRIPT2 = json.loads(json.dumps(SCRIPT))
    SCRIPT2['scenes'][0]['prompt'] = 'outra sala'
    assert client.put('/api/channels/meu-canal/scripts/roteiro.json', json=SCRIPT2).status_code == 200
    state = client.get('/api/channels/meu-canal/scripts/roteiro.json').json()
    assert state['scenes'][0]['image']['stale'] is True
    assert (channels / 'meu-canal' / 'roteiro.json.bak').exists()


def test_salvar_valida_o_roteiro(env):
    client, channels = env
    bad = {'scenes': [{'narration': ''}]}
    r = client.put('/api/channels/meu-canal/scripts/roteiro.json', json=bad)
    assert r.status_code == 422 and 'narration' in r.json()['detail']
    on_disk = json.loads((channels / 'meu-canal' / 'roteiro.json').read_text(encoding='utf-8'))
    assert on_disk == SCRIPT  # inválido não sobrescreve


def test_arquivos_so_das_pastas_permitidas(env):
    client, channels = env
    (channels / 'meu-canal' / '.env').write_text('GEMINI_API_KEY=segredo')
    (channels / 'meu-canal' / 'output' / 'preview.mp4').write_bytes(b'0000')
    assert client.get('/api/channels/meu-canal/media/output/preview.mp4').status_code == 200
    for url in ('/api/channels/meu-canal/media/output/..%2F.env',
                '/api/channels/meu-canal/media/output/.env',
                '/api/channels/meu-canal/media/image/..%5Croteiro.json',
                '/api/channels/..%2F/scripts/roteiro.json',
                '/api/channels/meu-canal/scripts/..%2F..%2Fx.json'):
        assert client.get(url).status_code == 404, url


def test_env_nunca_devolve_o_valor(env):
    client, channels = env
    r = client.post('/api/channels/meu-canal/env', json={'key': 'GEMINI_API_KEY', 'value': 'abc123'})
    assert r.status_code == 200 and 'abc123' not in r.text
    assert r.json()['keys']['GEMINI_API_KEY'] == 'canal'
    assert 'abc123' not in client.get('/api/channels/meu-canal/scripts/roteiro.json').text
    assert client.post('/api/channels/meu-canal/env', json={'key': 'PATH', 'value': 'x'}).status_code == 422
    assert (channels / 'meu-canal' / '.env').read_text().strip() == 'GEMINI_API_KEY=abc123'


def test_criar_canal_e_roteiro(env):
    client, channels = env
    assert client.post('/api/channels', json={'name': 'Meu Novo'}).json()['name'] == 'meu-novo'
    assert (channels / 'meu-novo' / 'roteiro_inicial.json').exists()
    assert client.post('/api/channels', json={'name': 'meu-novo'}).status_code == 409
    assert client.post('/api/channels', json={'name': '../x'}).status_code == 422
    assert client.post('/api/channels/meu-novo/scripts', json={'name': 'ep2'}).json() == {'script': 'ep2.json'}


def test_build_command():
    cmd = build_command('py', 'main.py', 'r.json', 'preview', provider='gemini', regen='1,3', no_voice=True)
    assert cmd == ['py', '-u', 'main.py', '--script', 'r.json', '--preview', '--image-provider', 'gemini',
                   '--regen', '1,3', '--strict-images', '--no-voice', '--output', 'output/preview.mp4']
    assert '--no-voice' not in build_command('py', 'm', 'r', 'images', no_voice=True)
    for kwargs in ({'mode': 'x'}, {'mode': 'images', 'regen': '1;rm'}, {'mode': 'images', 'provider': 'zzz'}):
        with pytest.raises(JobError):
            build_command('py', 'm', 'r', **kwargs)


def _wait(client, status, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        snap = client.get('/api/jobs/current').json()
        if snap and snap['status'] == status:
            return snap
        time.sleep(0.1)
    raise AssertionError(f'job não chegou a {status}: {snap}')


def test_job_ciclo_completo_com_progresso(env):
    client, _ = env
    assert client.get('/api/jobs/current').json() is None
    r = client.post('/api/jobs', json={'channel': 'meu-canal', 'script': 'roteiro.json', 'mode': 'render'})
    assert r.status_code == 200
    snap = _wait(client, 'done')
    assert snap['percent'] == 1.0 and snap['returncode'] == 0
    assert any('[2/2] Cena 2' in ln for ln in snap['lines'])
    assert any('revisão' in ln for ln in snap['lines'])  # acentos chegam íntegros
    tail = client.get(f'/api/jobs/current?since={snap["offset"]}').json()
    assert tail['lines'] == []


def test_job_cancelar(env):
    client, _ = env
    # o main.py falso dorme quando recebe --slow; build_command não aceita essa flag, então
    # ela é acrescentada por fora
    import webui.jobs as jobs_mod
    original = jobs_mod.build_command
    jobs_mod.build_command = lambda *a, **k: original(*a, **k) + ['--slow']
    try:
        assert client.post('/api/jobs', json={'channel': 'meu-canal', 'script': 'roteiro.json',
                                              'mode': 'render'}).status_code == 200
        assert client.post('/api/jobs', json={'channel': 'meu-canal', 'script': 'roteiro.json',
                                              'mode': 'render'}).status_code == 409
        assert client.post('/api/jobs/cancel').json() == {'cancelled': True}
        snap = _wait(client, 'cancelled')
        assert snap['label'] == 'Cancelado'
    finally:
        jobs_mod.build_command = original


def test_job_com_erro(env):
    client, _ = env
    import webui.jobs as jobs_mod
    original = jobs_mod.build_command
    jobs_mod.build_command = lambda *a, **k: original(*a, **k) + ['--fail']
    try:
        client.post('/api/jobs', json={'channel': 'meu-canal', 'script': 'roteiro.json', 'mode': 'images'})
        snap = _wait(client, 'error')
        assert snap['returncode'] == 3
    finally:
        jobs_mod.build_command = original


# ------------------------------------------------------------------ biblioteca de mídia e prévia por cena
import shutil
import subprocess

needs_ffmpeg = pytest.mark.skipif(not (shutil.which('ffmpeg') and shutil.which('ffprobe')),
                                  reason='FFmpeg não encontrado')


def test_nome_seguro_de_arquivo():
    from webui.library import safe_name
    assert safe_name('Ação  do dia (1).MOV') == 'Acao_do_dia_1.mov'
    assert safe_name('..\..\etc\passwd.mp4') == 'passwd.mp4'
    assert safe_name('C:/x/y/clip.webm') == 'clip.webm'
    assert safe_name('.mp4') is None  # arquivo oculto, sem nome
    assert safe_name('___.mp4') == 'video.mp4'
    assert safe_name('virus.exe') is None and safe_name('semextensao') is None


def test_build_command_cena_unica():
    cmd = build_command('py', 'main.py', 'r.json', 'scene', scene=3, no_voice=True)
    assert cmd == ['py', '-u', 'main.py', '--script', 'r.json', '--scenes', '3-3', '--res', '1280x720',
                   '--strict-images', '--no-voice', '--output', 'output/cena_03.mp4']
    for bad in (None, 0, -1, True, '2'):
        with pytest.raises(JobError):
            build_command('py', 'm', 'r', 'scene', scene=bad)


def test_importar_rejeita_formato_e_arquivo_que_nao_e_video(env):
    client, channels = env
    assert client.put('/api/channels/meu-canal/library/documento.txt', content=b'abc').status_code == 422
    r = client.put('/api/channels/meu-canal/library/falso.mp4', content=b'isto nao e um video')
    assert r.status_code == 422
    lib = channels / 'meu-canal' / 'assets' / 'media'
    assert not lib.exists() or list(lib.iterdir()) == []  # nada sobra (nem .part)
    assert client.put('/api/channels/meu-canal/library/vazio.mp4', content=b'').status_code == 422
    assert client.delete('/api/channels/meu-canal/library/inexistente.mp4').status_code == 404


@needs_ffmpeg
def test_biblioteca_importar_listar_usar_na_cena_e_apagar(env, tmp_path):
    client, channels = env
    clip = tmp_path / 'amostra.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=duration=2:size=160x120:rate=10',
                    '-pix_fmt', 'yuv420p', str(clip)], check=True)
    r = client.put('/api/channels/meu-canal/library/Minha%20Amostra.MP4', content=clip.read_bytes())
    assert r.status_code == 200, r.text
    item = r.json()
    assert item['name'] == 'Minha_Amostra.mp4'  # sem espaço, extensão minúscula
    assert item['duration'] == pytest.approx(2, abs=0.3) and item['thumb']
    assert client.get(item['thumb']).status_code == 200
    assert client.get(item['url']).status_code == 200
    again = client.put('/api/channels/meu-canal/library/Minha_Amostra.mp4', content=clip.read_bytes()).json()
    assert again['name'] == 'Minha_Amostra-2.mp4'  # nunca sobrescreve
    assert [i['name'] for i in client.get('/api/channels/meu-canal/library').json()] \
        == ['Minha_Amostra-2.mp4', 'Minha_Amostra.mp4'] or len(client.get('/api/channels/meu-canal/library').json()) == 2

    script = json.loads(json.dumps(SCRIPT))
    script['scenes'][0] = {'id': 'abertura', 'title': 'V', 'narration': 'Olá.', 'video': 'assets/media/Minha_Amostra.mp4'}
    script['scenes'].append({'id': 'sem-arquivo', 'title': 'S', 'narration': 'Oi.', 'layout': 'video'})
    script['scenes'].append({'id': 'sumiu', 'title': 'X', 'narration': 'Oi.', 'video': 'assets/media/nao_existe.mp4'})
    assert client.put('/api/channels/meu-canal/scripts/roteiro.json', json=script).status_code == 200
    scenes = client.get('/api/channels/meu-canal/scripts/roteiro.json').json()['scenes']
    assert scenes[0]['layout'] == 'video' and scenes[0]['video']['in_library'] is True
    assert scenes[0]['video']['thumb'] and scenes[0]['video']['duration']
    assert scenes[2]['video'] == {'path': None, 'exists': False, 'in_library': False}  # rascunho sem arquivo
    assert scenes[3]['video']['exists'] is False and scenes[3]['video']['path'].endswith('nao_existe.mp4')

    assert client.delete('/api/channels/meu-canal/library/Minha_Amostra.mp4').status_code == 200
    assert client.delete('/api/channels/meu-canal/library/..%2Froteiro.json').status_code in (404, 405)
    assert (channels / 'meu-canal' / 'roteiro.json').exists()


def test_previas_por_cena_aparecem_no_estado(env):
    client, channels = env
    out = channels / 'meu-canal' / 'output'
    (out / 'cena_02.mp4').write_bytes(b'0000')
    (out / 'cena_xx.mp4').write_bytes(b'0000')
    state = client.get('/api/channels/meu-canal/scripts/roteiro.json').json()
    assert list(state['outputs']['scenes']) == ['2']
