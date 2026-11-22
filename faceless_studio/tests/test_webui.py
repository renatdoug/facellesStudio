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
