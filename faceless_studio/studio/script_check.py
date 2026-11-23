"""Verificação de roteiros além do `validate_script()` (que só recusa o que impede de renderizar).

`check()` devolve avisos NÃO bloqueantes, cada um com cena e campo, em três níveis:
  - "erro":     vai falhar ao renderizar (ex.: gráfico com rótulos e valores de tamanhos diferentes);
  - "verificar": dado ou afirmação que uma pessoa precisa conferir antes de publicar;
  - "aviso":    algo estranho, mas que não impede o vídeo (ex.: campo desconhecido, provavelmente um erro de digitação).

Serve a importação de roteiros escritos por IA (guia_roteiro_ia.md) e ao editor.
"""
import difflib
from pathlib import Path

from . import layouts, subtitles, toon, video

# Campos que o motor lê. Mantido em sincronia com o guia (tests/test_import.py confere os dois).
SCRIPT_KEYS = ('title', 'channel', 'theme', 'voice', 'rate', 'resolution', 'fps', 'subtitles', 'default_transition', 'pause',
               'music', 'music_volume_db', 'motion_amount', 'font_bold', 'font_regular', 'images', 'scenes',
               'revisar', 'fontes', 'toon')
SCENE_KEYS = ('id', 'title', 'headline', 'narration', 'prompt', 'image', 'video', 'video_start', 'video_end',
              'layout', 'transition', 'motion', 'motion_amount', 'overlay_title', 'callouts', 'chapter', 'visual',
              'items', 'number', 'chart', 'compare', 'quote', 'revisar', 'speaker', 'emotion', 'reaction', 'gesture',
              'camera', 'voice')
CHART_KEYS = ('type', 'labels', 'values', 'series', 'unit', 'decimals', 'highlight', 'source', 'on_words',
              'orient', 'zero', 'animate', 'on_word', 'at')
NUMBER_KEYS = ('value', 'decimals', 'prefix', 'suffix', 'label', 'source', 'on_word', 'at')
THEMES = ('health', 'geek')


def _issue(level, scene, field, message):
    return {'level': level, 'scene': scene, 'field': field, 'message': message}


def _unknown(obj, known, scene, where):
    out = []
    for key in obj:
        if key in known:
            continue
        guess = difflib.get_close_matches(key, known, n=1, cutoff=0.7)
        hint = f' Quis dizer "{guess[0]}"?' if guess else ''
        out.append(_issue('aviso', scene, key, f'Campo desconhecido {where} "{key}" (será ignorado).{hint}'))
    return out


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _check_chart(spec, n):
    out = []
    if not isinstance(spec, dict):
        return [_issue('erro', n, 'chart', '"chart" deve ser um objeto com "type", "labels" e "values".')]
    out += _unknown(spec, CHART_KEYS, n, 'em "chart"')
    kind = spec.get('type', 'bar')
    if kind not in ('bar', 'barh', 'line'):
        out.append(_issue('erro', n, 'chart.type', f'Tipo de gráfico "{kind}" inválido. Use bar, barh ou line.'))
    labels = spec.get('labels')
    if not isinstance(labels, list) or not labels:
        return out + [_issue('erro', n, 'chart.labels', 'O gráfico precisa de "labels" (lista de rótulos).')]
    series = spec.get('series')
    if series is not None:
        if not isinstance(series, list) or not series or not all(isinstance(s, dict) for s in series):
            return out + [_issue('erro', n, 'chart.series', '"series" deve ser uma lista de {"name", "values"}.')]
        groups = [(f'chart.series[{k}].values', s.get('values')) for k, s in enumerate(series)]
    else:
        groups = [('chart.values', spec.get('values'))]
    for field, values in groups:
        if not isinstance(values, list) or len(values) != len(labels):
            size = len(values) if isinstance(values, list) else 0
            out.append(_issue('erro', n, field, f'"{field.split(".", 1)[1]}" tem {size} valor(es) e há {len(labels)} '
                                                f'rótulo(s): precisam ter o mesmo tamanho.'))
        elif not all(_is_num(v) for v in values):
            out.append(_issue('erro', n, field, 'Os valores do gráfico precisam ser números (sem aspas).'))
    on_words = spec.get('on_words')
    if on_words is not None and (not isinstance(on_words, list) or len(on_words) > len(labels)):
        out.append(_issue('aviso', n, 'chart.on_words', '"on_words" deve ser uma lista com no máximo um item por rótulo.'))
    source = str(spec.get('source', '')).strip()
    if not source:
        out.append(_issue('verificar', n, 'chart.source', 'Gráfico sem fonte: informe a origem do dado (autor, revista, ano) em "source".'))
    elif 'ilustrativ' in source.lower() or 'verificar' in source.lower():
        out.append(_issue('verificar', n, 'chart.source', f'Dados marcados como "{source}": substitua pelos dados '
                                                          f'reais e cite a fonte antes de publicar.'))
    return out


def _check_number(spec, n):
    if not isinstance(spec, dict):
        return [_issue('erro', n, 'number', '"number" deve ser um objeto com "value".')]
    out = _unknown(spec, NUMBER_KEYS, n, 'em "number"')
    if not _is_num(spec.get('value')):
        out.append(_issue('erro', n, 'number.value', '"number.value" precisa ser um número (sem aspas).'))
    source = str(spec.get('source', '')).strip()
    if not source:
        out.append(_issue('verificar', n, 'number.source', 'Número sem fonte: informe a origem do dado (autor, revista, ano) em "source".'))
    elif 'ilustrativ' in source.lower() or 'verificar' in source.lower():
        out.append(_issue('verificar', n, 'number.source', f'Número marcado como "{source}": substitua pelo dado '
                                                           f'real e cite a fonte antes de publicar.'))
    return out


def _check_items(items, n):
    if not isinstance(items, list) or not items:
        return [_issue('erro', n, 'items', 'A lista precisa de "items" (lista com pelo menos 1 item).')]
    out = []
    for k, it in enumerate(items, 1):
        text = it.get('text') if isinstance(it, dict) else it
        if not isinstance(text, str) or not text.strip():
            out.append(_issue('erro', n, f'items[{k}]', f'Item {k} da lista sem "text".'))
    if len(items) > 6:
        out.append(_issue('aviso', n, 'items', f'{len(items)} itens: acima de 5 ou 6 a lista fica apertada na tela.'))
    return out


def _check_compare(spec, n):
    if not isinstance(spec, dict) or not isinstance(spec.get('left'), dict) or not isinstance(spec.get('right'), dict):
        return [_issue('erro', n, 'compare', '"compare" precisa de "left" e "right" (cada um com "title" e "items").')]
    out = []
    for side in ('left', 'right'):
        if not isinstance(spec[side].get('items', []), list):
            out.append(_issue('erro', n, f'compare.{side}.items', f'"compare.{side}.items" deve ser uma lista.'))
    return out


def check(data, project_dir=None):
    """Avisos de um roteiro já validado por `validate_script()`. `project_dir` (a pasta do roteiro)
    permite conferir se imagens e vídeos citados existem."""
    out = []
    if not isinstance(data, dict):
        return out
    out += _unknown(data, SCRIPT_KEYS, None, 'no roteiro')
    theme = data.get('theme')
    if theme is not None and theme not in THEMES:
        out.append(_issue('aviso', None, 'theme', f'Tema "{theme}" desconhecido: será usado o visual "health". '
                                                  f'Temas: {", ".join(THEMES)}.'))
    for note in data.get('revisar') or []:
        out.append(_issue('verificar', None, 'revisar', str(note)))
    scenes = data.get('scenes') if isinstance(data.get('scenes'), list) else []
    for n, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            continue
        out += _unknown(scene, SCENE_KEYS, n, 'na cena')
        try:
            layout = layouts.detect_layout(scene)
        except Exception:  # validate_script já recusa layout inválido
            continue
        if layout == 'list':
            out += _check_items(scene.get('items'), n)
        elif layout == 'number':
            out += _check_number(scene.get('number'), n)
        elif layout == 'chart':
            out += _check_chart(scene.get('chart'), n)
        elif layout == 'compare':
            out += _check_compare(scene.get('compare'), n)
        elif layout == 'quote':
            if not isinstance(scene.get('quote'), dict) or not str(scene['quote'].get('text', '')).strip():
                out.append(_issue('erro', n, 'quote.text', '"quote" precisa de "text".'))
        elif layout == 'image':
            if not scene.get('image') and not str(scene.get('prompt', '')).strip():
                out.append(_issue('erro', n, 'prompt', 'Cena de imagem sem "prompt" (nem "image").'))
        elif layout == 'video' and project_dir is not None:
            ref = scene.get('video')
            if not ref:
                out.append(_issue('erro', n, 'video', 'Cena de vídeo sem arquivo escolhido (campo "video").'))
            else:
                path = Path(ref) if Path(ref).is_absolute() else Path(project_dir) / ref
                if not path.is_file():
                    out.append(_issue('erro', n, 'video', f'Vídeo não encontrado: {ref}. Importe-o na biblioteca do canal.'))
        if scene.get('image') and project_dir is not None:
            path = Path(scene['image']) if Path(scene['image']).is_absolute() else Path(project_dir) / scene['image']
            if not path.is_file():
                out.append(_issue('erro', n, 'image', f'Imagem não encontrada: {scene["image"]}.'))
        words = len(str(scene.get('narration', '')).split())
        if words > 60:
            out.append(_issue('aviso', n, 'narration',
                              f'Narração longa ({words} palavras, ~{words / 2.5:.0f} s): considere dividir a cena.'))
        notes = scene.get('revisar')
        if notes is not None and not isinstance(notes, list):
            out.append(_issue('aviso', n, 'revisar', '"revisar" deve ser uma lista de textos.'))
        for note in notes if isinstance(notes, list) else []:
            out.append(_issue('verificar', n, 'revisar', str(note)))
    order = {'erro': 0, 'verificar': 1, 'aviso': 2}
    return sorted(out, key=lambda i: (order[i['level']], i['scene'] or 0))


# Valores aceitos pelos campos de escolha: o guia cita estas listas, e um teste confere que seguem iguais.
CHOICES = {'transition': video.ENTRIES, 'motion': video.MOTIONS, 'subtitles': subtitles.CAPTION_MODES,
           'layout': layouts.LAYOUTS, 'emotion': tuple(toon.EMOTIONS), 'gesture': toon.GESTURES, 'camera': toon.CAMERAS,
           'hair': toon.HAIRS}
