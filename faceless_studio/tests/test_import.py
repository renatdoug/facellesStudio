"""Importar roteiro de IA: extração do JSON, validação, avisos, criação sem sobrescrever e guia sincronizado."""
import hashlib
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from studio import script_check
from webui import importer
from webui.app import create_app

ROOT = Path(__file__).resolve().parent.parent
GUIDE = (ROOT / 'guia_roteiro_ia.md').read_text(encoding='utf-8')

SCRIPT = {
    'title': 'Teste de Importação',
    'channel': 'Canal X',
    'resolution': '1080x1920',
    'subtitles': 'pop',
    'scenes': [
        {'id': 'a', 'title': 'Abertura', 'narration': 'Olá, mundo.', 'prompt': 'a room'},
        {'id': 'b', 'title': 'Lista', 'narration': 'Três coisas.', 'items': [{'text': 'um'}, {'text': 'dois'}]},
    ],
}


def as_text(data=None, **extra):
    return json.dumps({**(data or SCRIPT), **extra}, ensure_ascii=False, indent=2)


@pytest.fixture
def env(tmp_path):
    channels = tmp_path / 'canais'
    ch = channels / 'meu-canal'
    (ch / 'assets' / 'media').mkdir(parents=True)
    (ch / 'output').mkdir()
    (ch / 'existente.json').write_text(json.dumps(SCRIPT), encoding='utf-8')
    (ch / 'assets' / 'media' / 'clipe.mp4').write_bytes(b'0000')
    (ch / 'output' / 'video_final.mp4').write_bytes(b'1111')
    client = TestClient(create_app(channels, ROOT), base_url='http://localhost')
    return client, channels


def snapshot(folder):
    """{caminho relativo: sha1} de todos os arquivos: para provar que nada existente mudou."""
    return {str(p.relative_to(folder)): hashlib.sha1(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob('*')) if p.is_file()}


# ------------------------------------------------------------------ extração e erros de JSON

def test_extrai_json_de_bloco_de_codigo_e_de_texto_em_volta():
    body = as_text()
    assert importer.extract_json(body) == (body, [])
    assert importer.extract_json('﻿' + body)[0] == body
    fenced, notes = importer.extract_json(f'Claro! Aqui está:\n```json\n{body}\n```\nEspero que ajude.')
    assert json.loads(fenced) == SCRIPT and notes
    loose, notes = importer.extract_json(f'Segue o roteiro: {body} Qualquer dúvida, avise.')
    assert json.loads(loose) == SCRIPT and notes


def test_json_invalido_diz_linha_coluna_e_a_causa_provavel():
    r = importer.analyze('{\n  "scenes": [\n    {"narration": "x",},\n  ]\n}')
    assert not r['ok'] and 'linha 3' in r['error']['message'] and 'vírgula sobrando' in r['error']['message']
    r = importer.analyze('{"title": “Olá”, "scenes": []}')
    assert not r['ok'] and 'aspas curvas' in r['error']['message']
    r = importer.analyze('{"scenes": [] // comentário\n}')
    assert not r['ok'] and 'comentários' in r['error']['message']
    assert 'Cole' in importer.analyze('   ')['error']['message']
    assert 'objeto' in importer.analyze('[1, 2]')['error']['message']
    assert not importer.analyze('x' * (importer.MAX_CHARS + 1))['ok']


def test_erros_do_validador_do_motor_indicam_a_cena_e_o_campo():
    bad = json.loads(as_text())
    bad['scenes'][1]['transition'] = 'wipe'
    r = importer.analyze(json.dumps(bad))
    assert not r['ok'] and r['error']['scene'] == 2
    assert 'Cena 2' in r['error']['message'] and 'transition' in r['error']['message']
    bad = json.loads(as_text())
    del bad['scenes'][0]['narration']
    r = importer.analyze(json.dumps(bad))
    assert r['error']['scene'] == 1 and 'narration' in r['error']['message']
    r = importer.analyze(as_text(subtitles='neon'))
    assert 'subtitles' in r['error']['message'] and r['error']['scene'] is None


# ------------------------------------------------------------------ avisos (script_check)

def issues(project_dir=None, **scene_extra):
    data = json.loads(as_text())
    data['scenes'].append({'id': 'x', 'narration': 'Cena extra.', **scene_extra})
    return importer.analyze(json.dumps(data), project_dir)['issues']


def find(found, level, scene, field):
    return [i for i in found if (i['level'], i['scene'], i['field']) == (level, scene, field)]


def test_avisos_de_conteudo_apontam_cena_e_campo(tmp_path):
    f = issues(chart={'type': 'bar', 'labels': ['a', 'b', 'c'], 'values': [1, 2], 'source': 'IBGE'})
    assert find(f, 'erro', 3, 'chart.values')  # 2 valores e 3 rótulos
    f = issues(chart={'type': 'bar', 'labels': ['a'], 'values': ['10'], 'source': 'IBGE'})
    assert find(f, 'erro', 3, 'chart.values')  # número entre aspas
    assert find(issues(layout='list'), 'erro', 3, 'items')
    assert find(issues(number={'value': 'muitos'}), 'erro', 3, 'number.value')
    assert find(issues(layout='quote'), 'erro', 3, 'quote.text')
    assert find(issues(compare={'left': {}}), 'erro', 3, 'compare')
    assert not find(issues(layout='video'), 'erro', 3, 'video')  # sem a pasta do canal, não dá para conferir
    assert find(issues(tmp_path, layout='video'), 'erro', 3, 'video')  # com a pasta: vídeo não escolhido
    assert find(issues(tmp_path, video='assets/media/x.mp4'), 'erro', 3, 'video')  # arquivo inexistente


def test_dados_a_verificar_e_marcados_antes_de_publicar():
    f = issues(chart={'type': 'bar', 'labels': ['a'], 'values': [1]})
    assert find(f, 'verificar', 3, 'chart.source')  # sem fonte
    f = issues(chart={'type': 'bar', 'labels': ['a'], 'values': [1], 'source': 'Dados ilustrativos'})
    assert find(f, 'verificar', 3, 'chart.source')
    f = issues(number={'value': 5, 'source': 'A VERIFICAR'})
    assert find(f, 'verificar', 3, 'number.source')
    f = issues(number={'value': 5, 'source': 'Ministério da Saúde, 2023'})
    assert not find(f, 'verificar', 3, 'number.source')  # fonte real: sem aviso
    f = issues(revisar=['Conferir a conta: 12 x 3,6'])
    assert [i['message'] for i in find(f, 'verificar', 3, 'revisar')] == ['Conferir a conta: 12 x 3,6']
    data = json.loads(as_text(revisar=['Vale para o vídeo todo']))
    assert find(importer.analyze(json.dumps(data))['issues'], 'verificar', None, 'revisar')


def test_campo_desconhecido_vira_aviso_com_sugestao():
    f = issues(headlines='X', narracao='y')
    texto = [i['message'] for i in f if i['level'] == 'aviso']
    assert any('headlines' in t and '"headline"' in t for t in texto)
    r = importer.analyze(as_text(subtitle='pop', theme='neon'))
    msgs = [i['message'] for i in r['issues']]
    assert any('subtitle' in m and '"subtitles"' in m for m in msgs) and any('neon' in m for m in msgs)
    assert r['ok']  # aviso nunca bloqueia
    ordem = [i['level'] for i in r['issues']]
    assert ordem == sorted(ordem, key={'erro': 0, 'verificar': 1, 'aviso': 2}.get)


# ------------------------------------------------------------------ API: pré-visualizar

def test_previa_devolve_resumo_e_nao_grava_nada(env):
    client, channels = env
    before = snapshot(channels)
    r = client.post('/api/import/preview', json={'text': as_text(), 'channel': 'meu-canal'}).json()
    assert r['ok'] and 'data' not in r
    s = r['summary']
    assert (s['title'], s['format'], s['subtitles']) == ('Teste de Importação', 'Vertical 9:16', 'pop')
    assert [c['layout'] for c in s['scenes']] == ['image', 'list'] and s['seconds'] > 0
    assert snapshot(channels) == before
    r = client.post('/api/import/preview', json={'text': '{"scenes": [}'}).json()
    assert not r['ok'] and r['error']['message'].startswith('JSON inválido')
    assert client.post('/api/import/preview', json={'text': as_text(), 'channel': 'nao-existe'}).status_code == 404


def test_previa_confere_videos_na_pasta_do_canal(env):
    client, _ = env
    data = json.loads(as_text())
    data['scenes'][0] = {'id': 'v', 'narration': 'Vídeo.', 'video': 'assets/media/clipe.mp4'}
    ok = client.post('/api/import/preview', json={'text': json.dumps(data), 'channel': 'meu-canal'}).json()
    assert not find(ok['issues'], 'erro', 1, 'video')  # existe na biblioteca do canal
    data['scenes'][0]['video'] = 'assets/media/sumiu.mp4'
    miss = client.post('/api/import/preview', json={'text': json.dumps(data), 'channel': 'meu-canal'}).json()
    assert find(miss['issues'], 'erro', 1, 'video')


# ------------------------------------------------------------------ API: importar

def test_importar_cria_projeto_novo_e_preserva_todo_o_resto(env):
    client, channels = env
    ch = channels / 'meu-canal'
    before = snapshot(ch)
    r = client.post('/api/import', json={'text': as_text(), 'channel': 'meu-canal'})
    assert r.status_code == 200 and r.json() == {'channel': 'meu-canal', 'script': 'teste-de-importacao.json'}
    after = snapshot(ch)
    assert set(after) - set(before) == {'teste-de-importacao.json'}  # só um arquivo novo
    assert {k: v for k, v in after.items() if k in before} == before  # nada existente mudou (nem .bak)
    assert json.loads((ch / 'teste-de-importacao.json').read_text(encoding='utf-8')) == SCRIPT
    assert 'teste-de-importacao.json' in [s for c in client.get('/api/channels').json() for s in c['scripts']]


def test_importar_nunca_sobrescreve_nome_repetido(env):
    client, channels = env
    ch = channels / 'meu-canal'
    names = [client.post('/api/import', json={'text': as_text(), 'channel': 'meu-canal'}).json()['script']
             for _ in range(3)]
    assert names == ['teste-de-importacao.json', 'teste-de-importacao-2.json', 'teste-de-importacao-3.json']
    # nome escolhido que colide com roteiro existente
    named = client.post('/api/import', json={'text': as_text(), 'channel': 'meu-canal', 'name': 'existente'}).json()
    assert named['script'] == 'existente-2.json'
    assert json.loads((ch / 'existente.json').read_text(encoding='utf-8')) == SCRIPT  # original intacto


def test_importar_normaliza_o_nome_e_aceita_texto_em_volta(env):
    client, channels = env
    text = 'Aqui está:\n```json\n' + as_text() + '\n```'
    r = client.post('/api/import', json={'text': text, 'channel': 'meu-canal', 'name': '../Ação Épica!! 2'})
    assert r.status_code == 200 and r.json()['script'] == 'acao-epica-2.json'
    assert not (channels / 'acao-epica-2.json').exists()  # nada fora da pasta do canal
    r = client.post('/api/import', json={'text': as_text(title=''), 'channel': 'meu-canal'})
    assert r.json()['script'] == 'roteiro-importado.json'


def test_importar_invalido_nao_cria_nada(env):
    client, channels = env
    before = snapshot(channels)
    bad = json.loads(as_text())
    bad['scenes'][0]['motion'] = 'spin'
    r = client.post('/api/import', json={'text': json.dumps(bad), 'channel': 'meu-canal'})
    assert r.status_code == 422 and 'Cena 1' in r.json()['detail'] and 'motion' in r.json()['detail']
    assert client.post('/api/import', json={'text': '{', 'channel': 'meu-canal'}).status_code == 422
    assert client.post('/api/import', json={'text': as_text()}).status_code == 422  # sem canal
    assert client.post('/api/import', json={'text': as_text(), 'channel': 'nao-existe'}).status_code == 404
    assert snapshot(channels) == before


def test_importar_respeita_a_protecao_de_origem(env):
    client, channels = env
    before = snapshot(channels)
    r = client.post('/api/import', json={'text': as_text(), 'channel': 'meu-canal'},
                    headers={'origin': 'http://evil.example'})
    assert r.status_code == 403 and snapshot(channels) == before


def test_importado_pode_ser_aberto_e_renderizado_no_editor(env):
    client, _ = env
    name = client.post('/api/import', json={'text': as_text(), 'channel': 'meu-canal'}).json()['script']
    state = client.get(f'/api/channels/meu-canal/scripts/{name}').json()
    assert [s['layout'] for s in state['scenes']] == ['image', 'list']
    assert state['warnings'] == [] or all(w['level'] != 'erro' for w in state['warnings'])


def test_estado_do_roteiro_inclui_avisos(env):
    client, channels = env
    broken = json.loads(as_text())
    broken['scenes'][1] = {'id': 'g', 'narration': 'x', 'chart': {'type': 'bar', 'labels': ['a', 'b'], 'values': [1]}}
    (channels / 'meu-canal' / 'quebrado.json').write_text(json.dumps(broken), encoding='utf-8')
    w = client.get('/api/channels/meu-canal/scripts/quebrado.json').json()['warnings']
    assert find(w, 'erro', 2, 'chart.values')


# ------------------------------------------------------------------ guia

def test_guia_e_servido_pela_api(env):
    client, _ = env
    assert client.get('/api/guide').json()['text'] == GUIDE


def test_exemplo_do_guia_e_valido_e_sem_erros():
    example = re.search(r'```json\n(\{.*?\n\})\n```', GUIDE, re.DOTALL).group(1)
    r = importer.analyze(example)
    assert r['ok'], r['error']
    assert not [i for i in r['issues'] if i['level'] in ('erro', 'aviso')]  # só "verificar", como pede o guia
    assert any(i['level'] == 'verificar' for i in r['issues'])
    assert 'A VERIFICAR' in example


def test_guia_cita_todos_os_campos_e_valores_que_o_motor_aceita():
    for group in (script_check.SCRIPT_KEYS, script_check.SCENE_KEYS, script_check.CHART_KEYS,
                  script_check.NUMBER_KEYS):
        missing = [k for k in group if f'`{k}`' not in GUIDE and f'"{k}"' not in GUIDE]
        assert not missing, f'o guia não menciona: {missing}'
    for field, values in script_check.CHOICES.items():
        missing = [v for v in values if f'`{v}`' not in GUIDE]
        assert not missing, f'o guia não lista valores de "{field}": {missing}'


def test_guia_tem_as_regras_de_honestidade_e_a_separacao_dos_tres_papeis():
    for trecho in ('Nunca invente', 'A VERIFICAR', '`revisar`', '`narration`', 'um único objeto JSON',
                   'Pedido', 'não use pacientes', '2,5 palavras'):
        assert trecho.lower() in GUIDE.lower(), trecho
