"""Roteiro em texto simples -> cenas (sem IA): divisão, opções, fontes, custo estimado e importação."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main as engine
from studio import script_check, text_script as ts
from webui import importer
from webui.app import create_app

ROOT = Path(__file__).resolve().parent.parent

TEXTO = """Título: UTI e respiração

Quase metade das admissões na UTI é respiratória. O Dr. Silva explica que isso ocorre, p. ex., em pneumonias graves. Outra parte vem do coração e do cérebro.

A equipe olha primeiro as vias aéreas. Depois, a respiração e a circulação.

Fontes:
- Autor et al., Revista Brasileira, 2023
- Ministério da Saúde, 2022
"""


# ------------------------------------------------------------------ divisão em frases e cenas

def test_frases_nao_quebram_em_abreviacoes_nem_iniciais():
    assert ts.split_sentences('O Dr. Silva chegou. Ele examinou o paciente.') == \
        ['O Dr. Silva chegou.', 'Ele examinou o paciente.']
    assert ts.split_sentences('Isso ocorre, p. ex., em pneumonias. Outra coisa.') == \
        ['Isso ocorre, p. ex., em pneumonias.', 'Outra coisa.']
    assert ts.split_sentences('Segundo J. Silva et al., o efeito é real. Fim.') == \
        ['Segundo J. Silva et al., o efeito é real.', 'Fim.']
    assert ts.split_sentences('Será que dói? Sim! Mas passa… Depois volta.') == \
        ['Será que dói?', 'Sim!', 'Mas passa…', 'Depois volta.']
    assert ts.split_sentences('Pressão de 1,5 mmHg. Em 2023, caiu.') == ['Pressão de 1,5 mmHg.', 'Em 2023, caiu.']


def test_agrupa_frases_ate_o_limite_e_frase_longa_fica_sozinha():
    frases = ['Um dois três quatro.', 'Cinco seis sete.', 'Oito nove.']  # 4, 3 e 2 palavras
    assert ts.group_sentences(frases, 8) == ['Um dois três quatro. Cinco seis sete.', 'Oito nove.']
    assert ts.group_sentences(frases, 100) == [' '.join(frases)]
    longa = ' '.join(['palavra'] * 30) + '.'
    assert ts.group_sentences(['Curta.', longa, 'Outra.'], 10) == ['Curta.', longa, 'Outra.']  # nunca corta no meio


def test_paragrafos_viram_cenas_e_paragrafos_longos_sao_divididos():
    corpo = 'Primeira cena curta.\n\nSegunda cena também curta.'
    assert ts.split_scenes(corpo, 14) == ['Primeira cena curta.', 'Segunda cena também curta.']
    longo = 'Frase número um aqui. Frase número dois aqui. Frase número três aqui.\n\nCurta.'
    assert ts.split_scenes(longo, 7) == ['Frase número um aqui.', 'Frase número dois aqui.',
                                         'Frase número três aqui.', 'Curta.']
    # texto corrido, sem parágrafos: quem decide são as frases
    assert ts.split_scenes('Uma frase. Outra frase. Mais uma frase.', 4) == ['Uma frase. Outra frase.', 'Mais uma frase.']
    assert ts.split_scenes('Quebra\nno meio\nda linha.', 14) == ['Quebra no meio da linha.']  # quebra de linha não é cena


def test_titulo_e_fontes_saem_da_narracao():
    titulo, corpo, fontes = ts.extract_parts(TEXTO)
    assert titulo == 'UTI e respiração'
    assert 'Fontes' not in corpo and 'Autor et al.' not in corpo and 'Título' not in corpo
    assert fontes == ['Autor et al., Revista Brasileira, 2023', 'Ministério da Saúde, 2022']
    assert ts.extract_parts('# Meu título\n\nTexto.')[0] == 'Meu título'
    assert ts.extract_parts('Texto.\n\nFonte: Revista X, 2020')[2] == ['Revista X, 2020']
    assert ts.extract_parts('Texto sem título.')[0] is None


# ------------------------------------------------------------------ montagem do roteiro

def test_padroes_do_vertical_e_do_horizontal():
    v, notas = ts.script_from_text(TEXTO)
    assert (v['resolution'], v['subtitles'], v['default_transition'], v['pause']) == ('1080x1920', 'pop', 'punch', 0.2)
    assert 'full-bleed' in v['images']['style'] and v['images']['provider'] == 'gemini'
    assert v['title'] == 'UTI e respiração' and v['fontes'][0].startswith('Autor et al.')
    assert [s['id'] for s in v['scenes']] == ['cena1', 'cena2', 'cena3', 'cena4']
    assert all(s['prompt'].startswith('Illustration that visually represents this idea: ') for s in v['scenes'])
    assert len(v['scenes']) >= 4 and any('Dr. Silva' in s['narration'] for s in v['scenes'])
    assert any('4 cenas' in n for n in notas) and any('fonte' in n for n in notas)
    h, _ = ts.script_from_text(TEXTO, {'format': 'horizontal'})
    assert (h['resolution'], h['subtitles'], h['default_transition']) == ('1920x1080', 'karaoke', 'cut')
    assert 'full-bleed' not in h['images']['style']
    assert len(h['scenes']) < len(v['scenes'])  # cenas "longas" no horizontal


def test_opcoes_imagens_fornecedor_voz_e_titulo():
    d, _ = ts.script_from_text('Texto de teste um. Texto dois.', {'images': 'nenhuma', 'title': 'Meu vídeo'})
    assert d['title'] == 'Meu vídeo' and all('prompt' not in s and s['headline'] for s in d['scenes'])
    d, _ = ts.script_from_text('Texto.', {'provider': 'none'})
    assert 'prompt' not in d['scenes'][0]  # sem fornecedor não há imagem
    d, _ = ts.script_from_text('Texto.', {'provider': 'openai', 'voice': 'pt-BR-AntonioNeural', 'channel': 'Canal X'})
    assert (d['images']['provider'], d['voice'], d['channel']) == ('openai', 'pt-BR-AntonioNeural', 'Canal X')
    # valores inválidos caem no padrão, em vez de gerar um roteiro quebrado
    d, _ = ts.script_from_text('Texto.', {'format': 'cinema', 'provider': 'x', 'voice': 'rm -rf', 'scene_size': 'gigante'})
    assert (d['resolution'], d['images']['provider'], d['voice']) == ('1080x1920', 'gemini', ts.DEFAULT_VOICE)
    assert ts.script_from_text('Opção de título na opção. Frase.', {'title': 'A'})[0]['title'] == 'A'
    assert ts.script_from_text('Uma frase bem comprida para o título derivado do texto aqui.')[0]['title'].startswith('Uma frase bem')


def test_texto_vazio_ou_so_com_fontes_levanta_erro():
    for texto in ('', '   \n\n ', 'Fonte: só uma fonte'):
        with pytest.raises(ValueError, match='texto para narrar'):
            ts.script_from_text(texto)


@pytest.mark.parametrize('opts', [{}, {'format': 'horizontal'}, {'format': 'square'}, {'images': 'nenhuma'},
                                  {'scene_size': 'longa'}])
def test_roteiro_gerado_sempre_passa_no_validador_do_motor_e_no_verificador(opts):
    data, _ = ts.script_from_text(TEXTO, opts)
    engine.validate_script(data)
    assert not [i for i in script_check.check(data) if i['level'] in ('erro', 'aviso')], script_check.check(data)


# ------------------------------------------------------------------ importação (analyze + API)

def test_analyze_detecta_texto_x_json_e_estima_o_custo():
    r = importer.analyze(TEXTO)
    assert r['ok'] and r['mode'] == 'texto' and r['summary']['title'] == 'UTI e respiração'
    s = r['summary']
    assert s['images'] == len(s['scenes']) and s['provider'] == 'gemini'
    assert s['cost_brl'] == round(s['images'] * importer.GEMINI_IMAGE_BRL, 2) and 0.6 < importer.GEMINI_IMAGE_BRL < 0.65
    assert importer.analyze(TEXTO, options={'provider': 'pollinations'})['summary']['cost_brl'] is None  # só o Gemini foi medido
    assert importer.analyze(TEXTO, options={'images': 'nenhuma'})['summary']['images'] == 0
    j = importer.analyze(json.dumps({'scenes': [{'narration': 'Olá.'}]}))
    assert j['ok'] and j['mode'] == 'json'
    fenced = importer.analyze('Segue:\n```json\n{"scenes": [{"narration": "Olá."}]}\n```')
    assert fenced['mode'] == 'json' and fenced['notes']
    assert importer.analyze('Fonte: só isso')['error']['message'].startswith('Não encontrei texto')


def test_texto_simples_com_chaves_no_meio_continua_sendo_texto():
    r = importer.analyze('O conjunto {1, 2, 3} tem três elementos. Fim.')
    assert r['ok'] and r['mode'] == 'texto'


@pytest.fixture
def env(tmp_path):
    channels = tmp_path / 'canais'
    ch = channels / 'meu-canal'
    ch.mkdir(parents=True)
    (ch / 'existente.json').write_text('{"scenes": [{"narration": "x"}]}', encoding='utf-8')
    return TestClient(create_app(channels, ROOT), base_url='http://localhost'), channels


def test_api_previa_e_importacao_de_texto_simples(env):
    client, channels = env
    opts = {'format': 'horizontal', 'images': 'nenhuma'}
    prev = client.post('/api/import/preview', json={'text': TEXTO, 'channel': 'meu-canal', 'options': opts}).json()
    assert prev['ok'] and prev['mode'] == 'texto' and prev['summary']['format'] == 'Horizontal 16:9'
    assert prev['summary']['images'] == 0 and 'data' not in prev
    before = {p.name: p.read_bytes() for p in (channels / 'meu-canal').iterdir()}
    r = client.post('/api/import', json={'text': TEXTO, 'channel': 'meu-canal', 'options': opts})
    assert r.status_code == 200 and r.json()['script'] == 'uti-e-respiracao.json'
    saved = json.loads((channels / 'meu-canal' / 'uti-e-respiracao.json').read_text(encoding='utf-8'))
    assert saved['resolution'] == '1920x1080' and saved['fontes'] and saved['scenes'][0]['narration'].startswith('Quase metade')
    again = client.post('/api/import', json={'text': TEXTO, 'channel': 'meu-canal', 'options': opts}).json()
    assert again['script'] == 'uti-e-respiracao-2.json'  # nunca sobrescreve
    for nome, conteudo in before.items():
        assert (channels / 'meu-canal' / nome).read_bytes() == conteudo  # o que existia não mudou
    assert client.post('/api/import', json={'text': '  ', 'channel': 'meu-canal'}).status_code == 422
    # o roteiro importado abre no editor sem erros
    state = client.get('/api/channels/meu-canal/scripts/uti-e-respiracao.json').json()
    assert [s['layout'] for s in state['scenes']] and all(w['level'] != 'erro' for w in state['warnings'])


# ------------------------------------------------------------------ diálogo (cartum)

DIALOGO = """Título: O ninja que corre sobre a água

Leo: Eu vi num anime um ninja correndo sobre a água!
Ana (pensativa): Será que isso funciona de verdade?
Leo (convencido) [aponta]: Claro! É só correr rápido o bastante!
Ana [close]: Rápido quanto? Eu fiz a conta.
Leo (surpreso): Você fez a conta?!
Ana (convencida): A gente precisaria correr muito mais rápido do que qualquer humano consegue.
Leo (triste): Então eu fico com o barco.

Fonte: texto de exemplo
"""


def test_dialogo_vira_cartum_com_emocao_gesto_camera_e_vozes():
    data, notas = ts.script_from_text(DIALOGO)
    engine.validate_script(data)
    assert data['subtitles'] == 'topbox' and data['resolution'] == '1080x1920' and data['images']['provider'] == 'none'
    assert list(data['toon']['characters']) == ['leo', 'ana']
    assert data['toon']['characters']['leo']['voice'] == 'pt-BR-AntonioNeural'      # palpite pelo nome
    assert data['toon']['characters']['ana']['voice'] == 'pt-BR-FranciscaNeural'
    sc = data['scenes']
    assert [s['speaker'] for s in sc] == ['leo', 'ana', 'leo', 'ana', 'leo', 'ana', 'leo']
    assert [s['emotion'] for s in sc] == ['happy', 'thinking', 'smug', 'neutral', 'surprised', 'smug', 'sad']
    assert sc[2]['gesture'] == 'point' and sc[3]['camera'] == 'speaker' and 'gesture' not in sc[0]
    assert all('[' not in s['narration'] and '(' not in s['narration'] and ':' not in s['narration'] for s in sc)
    assert data['title'] == 'O ninja que corre sobre a água' and data['fontes'] == ['texto de exemplo']
    assert any('Diálogo entre Leo e Ana' in n and '7 falas' in n for n in notas) and any('Vozes' in n for n in notas)


def test_emocao_automatica_pela_pontuacao_e_emocao_desconhecida_avisa():
    data, notas = ts.script_from_text('Ana: Você veio?\nLeo: Cheguei!\nAna (nervosinha): Sério?!\nLeo: Pois é.')
    assert [s['emotion'] for s in data['scenes']] == ['thinking', 'happy', 'surprised', 'neutral']
    assert any('nervosinha' in n for n in notas)


def test_fala_longa_e_dividida_mantendo_o_personagem_e_o_gesto_so_na_primeira():
    longa = ' '.join(['Esta é uma frase razoavelmente comprida de teste.'] * 4)
    data, _ = ts.script_from_text(f'Ana [aponta]: {longa}\nLeo: Entendi.\nAna: Ok.')
    ana = [s for s in data['scenes'] if s['speaker'] == 'ana']
    assert len(ana) >= 3 and ana[0].get('gesture') == 'point' and 'gesture' not in ana[1]
    assert all(len(s['narration'].split()) <= ts.MAX_DIALOGUE_WORDS + 8 for s in data['scenes'])


def test_so_e_dialogo_com_exatamente_dois_nomes_e_maioria_de_falas():
    for texto in ('Importante: isso vale.\n\nOutro parágrafo qualquer.',                      # 1 nome
                  'Ana: oi\nLeo: oi\nBia: oi',                                                # 3 nomes
                  'Ana: oi\nLeo: oi',                                                         # só 2 falas
                  'Texto solto um.\nTexto solto dois.\nTexto solto três.\nAna: oi\nLeo: oi\nAna: tchau',):  # poucas falas
        data, _ = ts.script_from_text(texto)
        assert 'toon' not in data, texto  # continua sendo narração comum
    assert ts.parse_dialogue('Ana: oi\nLeo: oi\nAna: tchau') is not None


def test_voz_do_dialogo_vem_do_nome_nunca_se_repete_e_pode_ser_escolhida():
    # a opção "voice" é da narração: o painel da interface a envia sempre e NÃO pode igualar as duas vozes
    data, _ = ts.script_from_text('Leo: a\nAna: b\nLeo: c', {'voice': 'pt-BR-FranciscaNeural', 'format': 'horizontal'})
    v = {c['name']: c['voice'] for c in data['toon']['characters'].values()}
    assert v == {'Leo': 'pt-BR-AntonioNeural', 'Ana': 'pt-BR-FranciscaNeural'} and data['resolution'] == '1920x1080'
    # dois nomes com o mesmo palpite: a segunda voz é trocada para a outra
    data, _ = ts.script_from_text('Ana: a\nBia: b\nAna: c')
    assert {c['voice'] for c in data['toon']['characters'].values()} == {'pt-BR-FranciscaNeural', 'pt-BR-AntonioNeural'}
    data, _ = ts.script_from_text('Ana: a\nLeo: b\nAna: c', {'dialogue_voices': ['pt-BR-AntonioNeural', 'x']})
    assert data['toon']['characters']['ana']['voice'] == 'pt-BR-AntonioNeural'       # escolhida
    assert data['toon']['characters']['leo']['voice'] == 'pt-BR-FranciscaNeural'     # inválida => palpite, sem repetir a voz



def test_importar_dialogo_pela_api_cria_cenas_de_cartum_sem_imagens(env):
    client, channels = env
    prev = client.post('/api/import/preview', json={'text': DIALOGO, 'channel': 'meu-canal'}).json()
    assert prev['ok'] and prev['mode'] == 'texto'
    s = prev['summary']
    assert [c['layout'] for c in s['scenes']] == ['toon'] * 7 and s['images'] == 0 and s['cost_brl'] is None
    assert not [i for i in prev['issues'] if i['level'] in ('erro', 'aviso')]
    r = client.post('/api/import', json={'text': DIALOGO, 'channel': 'meu-canal'})
    assert r.status_code == 200
    state = client.get(f'/api/channels/meu-canal/scripts/{r.json()["script"]}').json()
    assert [x['layout'] for x in state['scenes']] == ['toon'] * 7 and state['script']['toon']['characters']['ana']['name'] == 'Ana'
