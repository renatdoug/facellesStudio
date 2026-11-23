"""Alinhamento LOCAL de palavras para narração GRAVADA (sem API, sem custo por uso).

O Edge TTS informa o instante de cada palavra; uma gravação de voz real não. Aqui os tempos vêm de duas fontes:
  1. um arquivo "tempos manuais" ao lado do áudio (`gravacao.wav` + `gravacao.palavras.json`, uma lista de
     `[inicio, fim, "palavra"]` em segundos) — para quem alinhou por outra ferramenta;
  2. o reconhecimento de fala local do `faster-whisper` (português do Brasil, roda no seu computador;
     instalação opcional: `pip install -r requirements-voz.txt`).
Os tempos NUNCA são reaproveitados do Edge TTS. Depois de alinhar, `assess()` mede o quanto do texto do roteiro foi
realmente ouvido na gravação e devolve um relatório: com pouca correspondência o motor RECUSA (em vez de mostrar uma
sincronização errada como se fosse boa); com correspondência média, avisa.
"""
from __future__ import annotations

import functools
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import subtitles
from .util import StudioError

DEFAULT_MODEL = os.environ.get('FACELESS_ALIGN_MODEL', 'small')  # tiny/base/small/medium: maior = mais preciso e mais lento
OK_COVERAGE = 0.85   # a partir daqui o alinhamento é considerado bom
MIN_COVERAGE = 0.60  # abaixo disso a sincronização não é confiável: recusa
MIN_PROB = 0.45      # confiança média do reconhecimento (faster-whisper) abaixo disso gera aviso
WORDS_PER_SECOND = (1.0, 6.0)  # faixa plausível de fala em português; fora dela algo está errado

SIDECAR_SUFFIX = '.palavras.json'


@dataclass
class Report:
    level: str                      # 'ok' | 'aviso' | 'erro'
    coverage: float                 # fração das palavras do roteiro ouvidas na gravação
    source: str                     # 'manual' ou 'whisper:<modelo>'
    mean_prob: float | None = None  # confiança média do reconhecimento (None nos tempos manuais)
    messages: list = field(default_factory=list)

    def summary(self) -> str:
        pct = f'{round(self.coverage * 100)}% das palavras do roteiro ouvidas'
        conf = '' if self.mean_prob is None else f', confiança {round(self.mean_prob * 100)}%'
        tag = {'ok': 'alinhamento OK', 'aviso': 'ALINHAMENTO APROXIMADO', 'erro': 'ALINHAMENTO NÃO CONFIÁVEL'}[self.level]
        return f'{tag} ({pct}{conf}; tempos: {self.source})'


def file_key(path) -> str:
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()[:16]


@functools.lru_cache(maxsize=2)
def _load_model(name: str):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise StudioError('Voz gravada precisa do alinhador local (faster-whisper). Instale com: '
                          'pip install -r requirements-voz.txt  (ou forneça os tempos em um arquivo '
                          f'"gravacao{SIDECAR_SUFFIX}" ao lado do áudio).')
    try:
        return WhisperModel(name, device='cpu', compute_type='int8')
    except Exception as err:  # modelo não baixado e sem internet, memória, etc.
        raise StudioError(f'Não consegui carregar o modelo de alinhamento "{name}" (na 1ª vez ele é baixado da internet, '
                          f'uma única vez): {err}')


def decode_16k(path):
    """Áudio como vetor float32 mono de 16 kHz (o que o reconhecedor espera), decodificado pelo FFmpeg do projeto.
    Assim aceita qualquer formato que o FFmpeg leia (wav, mp3, m4a, ogg, opus, flac...) e não depende do leitor de
    áudio interno do faster-whisper (que quebra com algumas versões do PyAV)."""
    import numpy as np
    p = subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-i', str(path), '-vn', '-f', 'f32le', '-ac', '1',
                        '-ar', '16000', '-'], capture_output=True)
    if p.returncode or not p.stdout:
        raise StudioError(f'Não consegui ler o áudio "{Path(path).name}" (formato não suportado ou arquivo corrompido): '
                          + p.stderr.decode('utf-8', 'replace')[-300:])
    return np.frombuffer(p.stdout, dtype=np.float32)


FRAME = 0.01  # s: resolução da energia da voz usada para ajustar as bordas das palavras


def refine_boundaries(events, samples, sr: int = 16000):
    """Ajusta o início e o fim de cada palavra à ENERGIA real da voz no áudio.

    O reconhecedor costuma "esticar" uma palavra para dentro do silêncio vizinho (achado no teste: a 1ª palavra de uma
    gravação, que tem silêncio antes, começava ~0,4 s cedo — a boca abria e a legenda aparecia antes da voz). Aqui o
    início sobe até o primeiro trecho realmente com voz dentro da palavra, e o fim desce até o último; nunca se
    afasta para fora da janela original e não mexe em palavras já bem posicionadas (tolerância de 60 ms)."""
    import numpy as np
    n = len(samples) // int(sr * FRAME)
    if n < 5 or not events:
        return events
    x = samples[:n * int(sr * FRAME)].reshape(n, int(sr * FRAME)).astype(np.float64)
    db = 20 * np.log10(np.sqrt((x ** 2).mean(axis=1)) + 1e-9)
    floor, peak = np.percentile(db, 10), np.percentile(db, 95)
    if peak - floor < 12:  # sem contraste (ruído constante ou áudio quase mudo): não dá para ajustar com segurança
        return events
    thr = max(floor + 8.0, floor + 0.2 * (peak - floor))
    voiced = db >= thr
    out = []
    for start, end, text in events:
        a, b = int(start / FRAME), min(n, int(np.ceil(end / FRAME)))
        idx = np.flatnonzero(voiced[a:b]) + a if b > a else np.array([], dtype=int)
        if idx.size:
            new_start = max(start, idx[0] * FRAME) if idx[0] * FRAME - start > 0.06 else start
            new_end = min(end, (idx[-1] + 1) * FRAME) if end - (idx[-1] + 1) * FRAME > 0.10 else end
            if new_end - new_start >= 0.05:
                start, end = new_start, new_end
        out.append([round(float(start), 3), round(float(end), 3), text])
    return out


def transcribe_words(path, model: str = DEFAULT_MODEL):
    """Reconhece a fala em português do Brasil e devolve ([[início, fim, texto], ...], [probabilidade de cada palavra])."""
    wm = _load_model(model)
    samples = decode_16k(path)
    try:
        segments, _info = wm.transcribe(samples, language='pt', word_timestamps=True, beam_size=5,
                                        condition_on_previous_text=False, vad_filter=True)
        events, probs = [], []
        for seg in segments:
            for w in seg.words or []:
                text = w.word.strip()
                if text:
                    events.append([round(float(w.start), 3), round(float(w.end), 3), text])
                    probs.append(float(w.probability))
    except StudioError:
        raise
    except Exception as err:
        raise StudioError(f'Falha ao reconhecer a fala de "{Path(path).name}": {err}')
    return refine_boundaries(events, samples), probs


def _valid_events(events) -> list:
    out = []
    for e in events:
        if not (isinstance(e, (list, tuple)) and len(e) == 3 and isinstance(e[2], str)
                and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in e[:2]) and 0 <= e[0] <= e[1]):
            raise StudioError('Tempos manuais inválidos: use uma lista de [início, fim, "palavra"] em segundos '
                              '(início <= fim, em ordem).')
        out.append([float(e[0]), float(e[1]), e[2]])
    if any(b[0] < a[0] for a, b in zip(out, out[1:])):
        raise StudioError('Tempos manuais fora de ordem: os inícios devem ser crescentes.')
    return out


def word_events(audio_path, cache_dir, model: str = DEFAULT_MODEL, transcribe=None):
    """Tempos das palavras de uma gravação: (eventos, probabilidades ou None, origem).
    Prioridade: arquivo de tempos manuais ao lado do áudio > cache > reconhecimento local."""
    audio_path = Path(audio_path)
    sidecar = audio_path.with_name(audio_path.stem + SIDECAR_SUFFIX)
    if sidecar.is_file():
        try:
            return _valid_events(json.loads(sidecar.read_text(encoding='utf-8'))), None, 'manual'
        except json.JSONDecodeError as err:
            raise StudioError(f'"{sidecar.name}" não é um JSON válido: {err}')
    key = file_key(audio_path)
    cached = Path(cache_dir) / f'alinhamento_{key}_{model}_v2.json'  # v2: bordas ajustadas à energia da voz
    if cached.is_file():
        data = json.loads(cached.read_text(encoding='utf-8'))
        return data['events'], data['probs'], f'whisper:{model}'
    events, probs = (transcribe or transcribe_words)(audio_path, model)
    cached.write_text(json.dumps({'events': events, 'probs': probs}, ensure_ascii=False), encoding='utf-8')
    return events, probs, f'whisper:{model}'


def assess(narration: str, events, probs, source: str, audio_seconds: float | None = None) -> Report:
    """Confere se o alinhamento é confiável. Não corrige nada: só diz a verdade sobre ele."""
    tokens = [t for t in narration.split() if subtitles._norm(t)]
    msgs = []
    if not events:
        return Report('erro', 0.0, source, None, ['Nenhuma fala foi reconhecida na gravação (silêncio, ruído ou áudio errado).'])
    coverage, missing = subtitles.match_coverage(narration, events, fuzzy=True)
    mean_prob = (sum(probs) / len(probs)) if probs else None
    level = 'ok'
    if coverage < MIN_COVERAGE:
        level = 'erro'
    elif coverage < OK_COVERAGE:
        level = 'aviso'
    if missing and level != 'ok':
        shown = ', '.join(m.strip('.,;:!?…"“”()') or m for m in missing[:8]) + ('…' if len(missing) > 8 else '')
        msgs.append(f'Palavras do roteiro que não foram ouvidas na gravação: {shown}. '
                    'A gravação diz outra coisa que o "narration", ou o áudio está difícil de reconhecer.')
    if mean_prob is not None and mean_prob < MIN_PROB and level == 'ok':
        level = 'aviso'
        msgs.append(f'O reconhecimento teve pouca confiança ({round(mean_prob * 100)}%): ruído de fundo ou fala muito baixa?')
    span = events[-1][1] - events[0][0]
    if tokens and span > 0.5:
        rate = len(tokens) / span
        if not WORDS_PER_SECOND[0] <= rate <= WORDS_PER_SECOND[1]:
            level = 'aviso' if level == 'ok' else level
            msgs.append(f'Ritmo de fala improvável ({rate:.1f} palavras/s): confira se o áudio é desta cena.')
    if audio_seconds is not None and events[-1][1] > audio_seconds + 0.5:
        level = 'erro'
        msgs.append('Os tempos passam do fim do áudio: os tempos manuais não pertencem a esta gravação.')
    if level == 'erro' and not msgs:
        msgs.append('Pouca correspondência entre o texto do roteiro e o que foi dito.')
    return Report(level, coverage, source, mean_prob, msgs)


_SAFE = re.compile(r'[^A-Za-z0-9_.-]+')


def recording_sheet(scenes, speaker: str):
    """Roteiro de gravação de um personagem: [(nº da cena, id, nome sugerido do arquivo, texto)]."""
    out = []
    for n, s in enumerate(scenes, 1):
        if s.get('speaker') == speaker:
            sid = _SAFE.sub('_', str(s.get('id') or f'cena{n}'))
            out.append((n, sid, f'{speaker}_{n:02}_{sid}.wav', s['narration'].strip()))
    return out
