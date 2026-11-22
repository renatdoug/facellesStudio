"""API local da interface web. Só orquestra: a geração continua no main.py (subprocesso)."""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Optional

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import main as engine
from studio import layouts
from studio.util import StudioError
from webui.jobs import PROVIDERS, JobError, JobManager

NAME_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,49}')
NEW_CHANNEL_RE = re.compile(r'[a-z0-9][a-z0-9_-]{1,49}')
SCRIPT_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,59}\.json')
MEDIA = {'image': ('assets/generated', {'.jpg', '.jpeg', '.png', '.webp'}),
         'output': ('output', {'.jpg', '.png', '.mp4', '.srt', '.txt'})}
ENV_KEYS = ('GEMINI_API_KEY', 'OPENAI_API_KEY', 'POLLINATIONS_API_KEY')
WORDS_PER_SECOND = 2.5  # estimativa para a linha do tempo (a duração real vem da voz)
LOCAL_HOSTS = {'localhost', '127.0.0.1', '[::1]'}


class JobRequest(BaseModel):
    channel: str
    script: str
    mode: str
    provider: Optional[str] = None
    regen: str = ''
    strict: bool = True
    no_voice: bool = False


class NameRequest(BaseModel):
    name: str


class EnvRequest(BaseModel):
    key: str
    value: str


def _hostname(host_header: str) -> str:
    host = (host_header or '').strip().lower()
    return host.rsplit(':', 1)[0] if not host.endswith(']') else host


def create_app(channels_dir, install_dir, jobs: JobManager | None = None, dist_dir=None) -> FastAPI:
    channels_dir, install_dir = Path(channels_dir).resolve(), Path(install_dir).resolve()
    jobs = jobs or JobManager(install_dir)
    app = FastAPI(title='Faceless Studio', docs_url=None, redoc_url=None, openapi_url=None)

    # O servidor só atende este computador. Host e Origin são conferidos para que uma página
    # qualquer aberta no navegador não consiga mandar o Studio gerar ou sobrescrever arquivos.
    @app.middleware('http')
    async def local_only(request: Request, call_next):
        if _hostname(request.headers.get('host', '')) not in LOCAL_HOSTS:
            return PlainTextResponse('Host não permitido.', status_code=403)
        origin = request.headers.get('origin')
        if request.method not in ('GET', 'HEAD') and origin:
            if origin.split('://', 1)[-1] != request.headers.get('host'):
                return PlainTextResponse('Origem não permitida.', status_code=403)
        return await call_next(request)

    # ---------------------------------------------------------------- helpers
    def channel_dir(name: str) -> Path:
        if not NAME_RE.fullmatch(name):
            raise HTTPException(404, 'Canal não encontrado.')
        path = (channels_dir / name).resolve()
        if path.parent != channels_dir or not path.is_dir():
            raise HTTPException(404, 'Canal não encontrado.')
        return path

    def script_path(channel: str, script: str) -> Path:
        folder = channel_dir(channel)
        if not SCRIPT_RE.fullmatch(script):
            raise HTTPException(404, 'Roteiro não encontrado.')
        path = folder / script
        if not path.is_file():
            raise HTTPException(404, 'Roteiro não encontrado.')
        return path

    def read_script(path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as err:
            raise HTTPException(422, f'Roteiro ilegível: {err}')

    def file_info(path: Path, url: str):
        if not path.is_file():
            return None
        mtime = int(path.stat().st_mtime)
        return {'url': f'{url}?v={mtime}', 'mtime': mtime, 'size': path.stat().st_size}

    def read_env_keys(folder: Path) -> dict:
        found = {}
        for source, path in (('canal', folder / '.env'), ('instalação', install_dir / '.env')):
            try:
                lines = path.read_text(encoding='utf-8').splitlines()
            except OSError:
                continue
            for line in lines:
                key, sep, value = line.partition('=')
                key = key.strip()
                if sep and key in ENV_KEYS and value.strip() and key not in found:
                    found[key] = source
        return {k: found.get(k) for k in ENV_KEYS}

    def write_json(path: Path, data: dict):
        tmp = path.with_name(path.name + '.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        if path.exists():
            shutil.copy2(path, path.with_name(path.name + '.bak'))
        os.replace(tmp, path)

    # ---------------------------------------------------------------- canais
    @app.get('/api/meta')
    def meta():
        return {'providers': list(PROVIDERS), 'layouts': list(layouts.LAYOUTS),
                'busy': (jobs.snapshot() or {}).get('status') == 'running'}

    @app.get('/api/channels')
    def list_channels():
        out = []
        for folder in sorted(p for p in channels_dir.iterdir() if p.is_dir()) if channels_dir.is_dir() else []:
            if not NAME_RE.fullmatch(folder.name):
                continue
            out.append({'name': folder.name, 'scripts': sorted(p.name for p in folder.glob('*.json')
                                                               if SCRIPT_RE.fullmatch(p.name))})
        return out

    @app.post('/api/channels')
    def create_channel(req: NameRequest):
        name = req.name.strip().lower().replace(' ', '-')
        if not NEW_CHANNEL_RE.fullmatch(name):
            raise HTTPException(422, 'Use letras sem acento, números, hífen ou sublinhado (mínimo 2).')
        folder = channels_dir / name
        if folder.exists():
            raise HTTPException(409, 'Já existe um canal com esse nome.')
        folder.mkdir(parents=True)
        sample = install_dir / 'roteiro_uti.json'
        if sample.exists():
            data = json.loads(sample.read_text(encoding='utf-8'))
        else:
            data = _blank_script()
        data['channel'] = name.replace('-', ' ').title()
        write_json(folder / 'roteiro_inicial.json', data)
        return {'name': name, 'scripts': ['roteiro_inicial.json']}

    @app.post('/api/channels/{channel}/scripts')
    def create_script(channel: str, req: NameRequest):
        folder = channel_dir(channel)
        name = req.name.strip().lower().replace(' ', '-')
        name = name if name.endswith('.json') else name + '.json'
        if not SCRIPT_RE.fullmatch(name):
            raise HTTPException(422, 'Nome inválido: use letras sem acento, números, hífen ou sublinhado.')
        if (folder / name).exists():
            raise HTTPException(409, 'Já existe um roteiro com esse nome.')
        data = _blank_script()
        data['channel'] = channel.replace('-', ' ').title()
        write_json(folder / name, data)
        return {'script': name}

    # ---------------------------------------------------------------- roteiro
    @app.get('/api/channels/{channel}/scripts/{script}')
    def get_state(channel: str, script: str):
        folder = channel_dir(channel)
        path = script_path(channel, script)
        data = read_script(path)
        manifest = {}
        try:
            manifest = json.loads((folder / 'assets/generated/manifest.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
        base = f'/api/channels/{channel}/media'
        scenes = []
        for idx, scene in enumerate(data.get('scenes') or [], 1):
            if not isinstance(scene, dict):
                continue
            try:
                layout = layouts.detect_layout(scene)
            except StudioError:
                layout = 'invalid'
            sid = str(scene.get('id') or f'{idx:02}')
            entry = manifest.get(sid)
            image = None
            if layout == 'image' and scene.get('image'):
                image = {'kind': 'file', 'url': None, 'stale': False}
            elif layout == 'image' and entry and (folder / 'assets/generated' / entry['file']).exists():
                image = {'kind': 'ai', 'url': f'{base}/image/{entry["file"]}',
                         'stale': entry.get('prompt') != scene.get('prompt'),
                         'provider': entry.get('provider'), 'prompt': entry.get('prompt')}
            words = len(str(scene.get('narration', '')).split())
            scenes.append({'index': idx, 'id': sid, 'layout': layout, 'image': image,
                           'seconds': round(words / WORDS_PER_SECOND + 0.8, 1)})
        out = folder / 'output'
        outputs = {'preview': file_info(out / 'preview.mp4', f'{base}/output/preview.mp4'),
                   'final': file_info(out / 'video_final.mp4', f'{base}/output/video_final.mp4'),
                   'sheet': file_info(out / 'revisao_imagens.jpg', f'{base}/output/revisao_imagens.jpg')}
        return {'script': data, 'scenes': scenes, 'outputs': outputs, 'keys': read_env_keys(folder)}

    @app.put('/api/channels/{channel}/scripts/{script}')
    def save_script(channel: str, script: str, data: dict[str, Any] = Body(...)):
        path = script_path(channel, script)
        try:
            engine.validate_script(data)
        except StudioError as err:
            raise HTTPException(422, str(err))
        write_json(path, data)
        return {'saved': True}

    @app.post('/api/channels/{channel}/env')
    def set_env(channel: str, req: EnvRequest):
        folder = channel_dir(channel)
        value = req.value.strip()
        if req.key not in ENV_KEYS:
            raise HTTPException(422, 'Chave não reconhecida.')
        if not value or re.search(r'[\r\n]', value):
            raise HTTPException(422, 'Valor inválido.')
        env = folder / '.env'
        lines = env.read_text(encoding='utf-8').splitlines() if env.exists() else []
        lines = [ln for ln in lines if ln.partition('=')[0].strip() != req.key]
        lines.append(f'{req.key}={value}')
        env.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        return {'keys': read_env_keys(folder)}  # nunca devolve o valor

    # ---------------------------------------------------------------- arquivos
    @app.get('/api/channels/{channel}/media/{kind}/{name}')
    def media(channel: str, kind: str, name: str):
        folder = channel_dir(channel)
        if kind not in MEDIA:
            raise HTTPException(404)
        sub, exts = MEDIA[kind]
        if '/' in name or '\\' in name or Path(name).suffix.lower() not in exts:
            raise HTTPException(404)
        path = (folder / sub / name).resolve()
        if path.parent != (folder / sub).resolve() or not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, headers={'Cache-Control': 'no-cache'})

    # ---------------------------------------------------------------- produção
    @app.post('/api/jobs')
    def start_job(req: JobRequest):
        path = script_path(req.channel, req.script)
        try:
            engine.validate_script(read_script(path))
        except StudioError as err:
            raise HTTPException(422, f'Roteiro inválido: {err}')
        try:
            job_id = jobs.start(path, req.mode, req.channel, req.script, provider=req.provider,
                                regen=req.regen, strict=req.strict, no_voice=req.no_voice)
        except JobError as err:
            raise HTTPException(409 if 'andamento' in str(err) else 422, str(err))
        return {'id': job_id}

    @app.get('/api/jobs/current')
    def current_job(since: int = 0):
        return JSONResponse(jobs.snapshot(max(since, 0)))

    @app.post('/api/jobs/cancel')
    def cancel_job():
        return {'cancelled': jobs.cancel()}

    # ---------------------------------------------------------------- front-end
    dist = Path(dist_dir) if dist_dir else Path(__file__).parent / 'frontend' / 'dist'
    if (dist / 'index.html').exists():
        app.mount('/', StaticFiles(directory=dist, html=True), name='frontend')
    else:
        @app.get('/')
        def missing_frontend():
            return PlainTextResponse('Front-end não compilado. Rode: cd webui/frontend && npm install && npm run build',
                                     status_code=503)
    return app


def _blank_script() -> dict:
    return {'title': 'Novo roteiro', 'channel': 'Meu canal', 'theme': 'health', 'voice': 'pt-BR-AntonioNeural',
            'images': {'provider': 'pollinations', 'style': 'editorial digital illustration, clean flat shapes, no text'},
            'scenes': [{'id': 'abertura', 'title': 'Abertura', 'headline': 'TÍTULO DO VÍDEO',
                        'narration': 'Escreva aqui a narração da primeira cena.',
                        'prompt': 'descreva a imagem desta cena'}]}
