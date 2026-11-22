"""Geração de imagens por IA com fornecedores intercambiáveis, cache e manifesto de revisão.

Fornecedores:
  pollinations  grátis (sem chave: lento, 1 imagem a cada ~16 s); com POLLINATIONS_API_KEY fica mais rápido
  openai        OPENAI_API_KEY      (Images API; modelo configurável, padrão gpt-image-2)
  gemini        GEMINI_API_KEY      (Nano Banana; padrão gemini-3.1-flash-image)
  comfyui       local, na sua GPU   (ComfyUI aberto + workflow exportado em formato API)
"""
import base64
import hashlib
import json
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .util import StudioError

DEFAULTS = {
    'openai': {'model': 'gpt-image-2', 'size': '1536x1024', 'quality': 'medium'},
    'gemini': {'model': 'gemini-3.1-flash-image', 'image_size': '2K'},
    'pollinations': {'model': 'flux', 'width': 1920, 'height': 1080},
    'comfyui': {'url': 'http://127.0.0.1:8188', 'workflow': 'comfyui/sdxl_api.json',
                'width': 1344, 'height': 768, 'checkpoint': 'sd_xl_base_1.0.safetensors', 'steps': 28},
}
NO_TEXT = 'no text, no letters, no words, no captions, no watermark, no logo'


class ImageGenError(Exception):
    pass


def load_dotenv(path):
    """Lê chaves de um arquivo .env simples (CHAVE=valor), sem sobrescrever variáveis já definidas."""
    path = Path(path)
    if not path.exists():
        return
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# ------------------------------------------------------------------ HTTP

def _http(url, data=None, headers=None, method=None, timeout=180, retries=3):
    body = json.dumps(data).encode('utf-8') if isinstance(data, (dict, list)) else data
    hdrs = {'User-Agent': 'FacelessStudio/0.3'}
    if isinstance(data, (dict, list)):
        hdrs['Content-Type'] = 'application/json'
    hdrs.update(headers or {})
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read(), r.headers.get('Content-Type', '')
        except urllib.error.HTTPError as e:
            detail = e.read().decode('utf-8', 'replace')[:600]
            last = ImageGenError(f'HTTP {e.code} em {urllib.parse.urlsplit(url).netloc}: {detail}')
            last.status = e.code
            if e.code in (429, 500, 502, 503, 504) and attempt + 1 < retries:
                time.sleep(4 * (attempt + 1) + random.random() * 2)
                continue
            raise last
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = ImageGenError(f'Sem conexão com {urllib.parse.urlsplit(url).netloc}: {e}')
            if attempt + 1 < retries:
                time.sleep(3 * (attempt + 1))
                continue
            raise last
    raise last


def _need_key(var):
    key = os.environ.get(var)
    if not key:
        raise ImageGenError(f'Defina a variável {var} (ou coloque no arquivo .env do projeto).')
    return key


# ------------------------------------------------------------------ fornecedores

def gen_openai(prompt, cfg, seed):
    key = _need_key('OPENAI_API_KEY')
    base = os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1').rstrip('/')
    payload = {'model': cfg['model'], 'prompt': prompt, 'size': cfg['size'],
               'quality': cfg['quality'], 'n': 1}
    raw, _ = _http(f'{base}/images/generations', payload, {'Authorization': f'Bearer {key}'}, timeout=300)
    data = json.loads(raw)
    item = (data.get('data') or [{}])[0]
    if item.get('b64_json'):
        return base64.b64decode(item['b64_json'])
    if item.get('url'):
        return _http(item['url'])[0]
    raise ImageGenError(f'Resposta da OpenAI sem imagem: {str(data)[:300]}')


def _gemini_extract(data):
    for cand in data.get('candidates', []):
        for part in (cand.get('content') or {}).get('parts', []):
            inline = part.get('inlineData') or part.get('inline_data')
            if inline and inline.get('data'):
                return base64.b64decode(inline['data'])
    reason = (data.get('promptFeedback') or {}).get('blockReason') or \
        ((data.get('candidates') or [{}])[0].get('finishReason'))
    raise ImageGenError(f'O Gemini não devolveu imagem (motivo: {reason}).')


def gen_gemini(prompt, cfg, seed):
    key = _need_key('GEMINI_API_KEY')
    base = os.environ.get('GEMINI_BASE_URL', 'https://generativelanguage.googleapis.com').rstrip('/')
    model = cfg['model']
    img = {'aspectRatio': cfg.get('aspect', '16:9')}
    if cfg.get('image_size') and 'lite' not in model:
        img['imageSize'] = cfg['image_size']
    contents = [{'parts': [{'text': prompt + '. Widescreen 16:9 composition.'}]}]
    # A API já usou nomes diferentes para a configuração de proporção; tentamos em ordem.
    attempts = [
        ('v1beta', {'responseModalities': ['IMAGE'], 'imageConfig': img}),
        ('v1', {'responseModalities': ['TEXT', 'IMAGE'], 'responseFormat': {'image': img}}),
        ('v1beta', {'responseModalities': ['TEXT', 'IMAGE']}),
    ]
    last = None
    for ver, gen_cfg in attempts:
        url = f'{base}/{ver}/models/{model}:generateContent'
        try:
            raw, _ = _http(url, {'contents': contents, 'generationConfig': gen_cfg},
                           {'x-goog-api-key': key}, timeout=300)
            return _gemini_extract(json.loads(raw))
        except ImageGenError as e:
            last = e
            if getattr(e, 'status', None) not in (400, 404):
                raise
    raise last


_last_free_call = [0.0]


def gen_pollinations(prompt, cfg, seed):
    key = os.environ.get('POLLINATIONS_API_KEY')
    q = urllib.parse.quote(prompt, safe='')
    params = urllib.parse.urlencode({'model': cfg['model'], 'width': cfg['width'], 'height': cfg['height'],
                                     'seed': seed, 'nologo': 'true'})
    if key:
        base = os.environ.get('POLLINATIONS_BASE_URL', 'https://gen.pollinations.ai').rstrip('/')
        url, headers = f'{base}/image/{q}?{params}', {'Authorization': f'Bearer {key}'}
    else:
        base = os.environ.get('POLLINATIONS_FREE_URL', 'https://image.pollinations.ai').rstrip('/')
        url, headers = f'{base}/prompt/{q}?{params}', {}
        wait = float(os.environ.get('POLLINATIONS_FREE_INTERVAL', 16)) - (time.time() - _last_free_call[0])
        if wait > 0:
            print(f'      (Pollinations grátis: aguardando {wait:.0f} s)', flush=True)
            time.sleep(wait)
        _last_free_call[0] = time.time()
    raw, ctype = _http(url, headers=headers, timeout=240)
    if not ctype.startswith('image/'):
        raise ImageGenError(f'Pollinations devolveu {ctype or "conteúdo desconhecido"}: {raw[:200]!r}')
    return raw


def _fill(obj, values):
    """Substitui {{CHAVE}} no workflow. Campo que é só o marcador recebe o valor com o tipo certo."""
    if isinstance(obj, dict):
        return {k: _fill(v, values) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_fill(v, values) for v in obj]
    if isinstance(obj, str):
        for k, v in values.items():
            mark = '{{' + k + '}}'
            if obj == mark:
                return v
            obj = obj.replace(mark, str(v))
    return obj


def gen_comfyui(prompt, cfg, seed, project_dir='.', install_dir=None):
    url = cfg['url'].rstrip('/')
    wf_path = Path(project_dir) / cfg['workflow']
    if not wf_path.exists() and install_dir is not None:
        wf_path = Path(install_dir) / cfg['workflow']  # workflow padrão vem com a instalação
    if not wf_path.exists():
        raise ImageGenError(f'Workflow do ComfyUI não encontrado: {wf_path}')
    wf = _fill(json.loads(wf_path.read_text(encoding='utf-8')), {
        'PROMPT': prompt, 'NEGATIVE': cfg.get('negative', 'text, watermark, blurry, deformed, lowres'),
        'SEED': seed, 'WIDTH': cfg['width'], 'HEIGHT': cfg['height'],
        'CHECKPOINT': cfg['checkpoint'], 'STEPS': cfg['steps']})
    raw, _ = _http(f'{url}/prompt', {'prompt': wf, 'client_id': 'faceless-studio'}, timeout=30)
    pid = json.loads(raw).get('prompt_id')
    if not pid:
        raise ImageGenError(f'ComfyUI recusou o workflow: {raw[:300]!r}')
    deadline = time.time() + float(cfg.get('timeout', 900))
    while time.time() < deadline:
        hist = json.loads(_http(f'{url}/history/{pid}', timeout=30)[0])
        entry = hist.get(pid)
        if entry:
            status = entry.get('status') or {}
            if status.get('status_str') == 'error':
                raise ImageGenError('O ComfyUI terminou com erro. Veja o console do ComfyUI.')
            for node in (entry.get('outputs') or {}).values():
                for img in node.get('images', []):
                    q = urllib.parse.urlencode({'filename': img['filename'], 'subfolder': img.get('subfolder', ''),
                                                'type': img.get('type', 'output')})
                    return _http(f'{url}/view?{q}', timeout=60)[0]
            if status.get('completed'):
                raise ImageGenError('O workflow terminou sem nó SaveImage/PreviewImage com saída.')
        time.sleep(1.0)
    raise ImageGenError('Tempo esgotado esperando o ComfyUI.')


def orientation_of(w, h):
    """'portrait' (9:16), 'square' (1:1) ou 'landscape' (16:9), pelo formato do vídeo."""
    ratio = w / h
    return 'portrait' if ratio < 0.83 else 'square' if ratio < 1.2 else 'landscape'


# Ajustes por formato: o padrão (DEFAULTS) é 16:9. Valores do roteiro ("images") continuam mandando.
ORIENTATION_CFG = {
    'portrait': {'openai': {'size': '1024x1536'}, 'gemini': {'aspect': '9:16'},
                 'pollinations': {'width': 1080, 'height': 1920}, 'comfyui': {'width': 768, 'height': 1344}},
    'square': {'openai': {'size': '1024x1024'}, 'gemini': {'aspect': '1:1'},
               'pollinations': {'width': 1080, 'height': 1080}, 'comfyui': {'width': 1024, 'height': 1024}},
}

PROVIDERS = {'openai': gen_openai, 'gemini': gen_gemini, 'pollinations': gen_pollinations,
             'comfyui': gen_comfyui}


# ------------------------------------------------------------------ cache + manifesto

class ImageBank:
    """Guarda as imagens geradas em assets/generated e lembra qual arquivo pertence a cada cena.
    Só gera de novo quando o prompt/estilo/fornecedor mudam ou quando você pede (--regen)."""

    def __init__(self, project_dir, settings, install_dir=None, orientation='landscape'):
        self.project_dir = Path(project_dir)
        self.install_dir = Path(install_dir) if install_dir else self.project_dir
        self.dir = self.project_dir / 'assets' / 'generated'
        self.dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.dir / 'manifest.json'
        try:
            self.manifest = json.loads(self.manifest_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            self.manifest = {}
        settings = dict(settings or {})
        self.provider = settings.pop('provider', 'pollinations')
        if self.provider not in PROVIDERS and self.provider != 'none':
            raise StudioError(f'Fornecedor de imagem "{self.provider}" inválido. Use: '
                              + ', '.join(list(PROVIDERS) + ['none']))
        self.style = settings.pop('style', '')
        self.base_seed = int(settings.pop('seed', 1234))
        self.cfg = dict(DEFAULTS.get(self.provider, {}))
        self.cfg.update(ORIENTATION_CFG.get(orientation, {}).get(self.provider, {}))
        self.cfg.update(settings)

    def full_prompt(self, prompt):
        parts = [prompt.strip().rstrip('.'), self.style.strip().rstrip('.'), NO_TEXT]
        return ', '.join(p for p in parts if p)

    def fingerprint(self, prompt):
        relevant = {k: v for k, v in self.cfg.items() if k not in ('url', 'timeout')}
        raw = json.dumps([self.provider, relevant, self.full_prompt(prompt)], sort_keys=True)
        return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]

    def get(self, scene_id, prompt, regen=False):
        """Devolve o caminho da imagem da cena, gerando se necessário."""
        fp = self.fingerprint(prompt)
        entry = self.manifest.get(scene_id)
        if entry and not regen and entry.get('fingerprint') == fp and (self.dir / entry['file']).exists():
            return self.dir / entry['file'], False
        if self.provider == 'none':
            raise ImageGenError('geração de imagens desligada ("provider": "none").')
        seed = random.randint(1, 2 ** 31 - 1) if regen else self.base_seed
        fn = PROVIDERS[self.provider]
        kwargs = ({'project_dir': self.project_dir, 'install_dir': self.install_dir}
                 if self.provider == 'comfyui' else {})
        data = fn(self.full_prompt(prompt), self.cfg, seed, **kwargs)
        ext = '.png' if data[:4] == b'\x89PNG' else '.jpg' if data[:2] == b'\xff\xd8' else '.webp'
        name = f'cena_{scene_id}_{fp[:8]}_{seed}{ext}'
        (self.dir / name).write_bytes(data)
        self.manifest[scene_id] = {'file': name, 'fingerprint': fp, 'prompt': prompt,
                                   'provider': self.provider, 'seed': seed}
        self.manifest_path.write_text(json.dumps(self.manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        return self.dir / name, True
