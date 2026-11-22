"""Execução do main.py como subprocesso, com log e progresso consultáveis pela interface."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

MODES = ('images', 'preview', 'render', 'scene')
PROVIDERS = ('pollinations', 'gemini', 'openai', 'comfyui', 'none')
_REGEN = re.compile(r'\d+(,\d+)*')
_RENDER_STEP = re.compile(r'^\[(\d+)/(\d+)\] Cena')
_IMAGES_TOTAL = re.compile(r'^Imagens por IA: (\d+) cena')
_IMAGE_DONE = re.compile(r'^\s+cena \d+: (gerada|do cache)')


class JobError(Exception):
    pass


def build_command(python, main_py, script, mode, provider=None, regen='', strict=True, no_voice=False,
                  scene=None):
    """Monta a linha de comando do main.py. Levanta JobError para entradas inválidas."""
    if mode not in MODES:
        raise JobError(f'Modo inválido: {mode}')
    cmd = [str(python), '-u', str(main_py), '--script', str(script)]
    if mode == 'images':
        cmd.append('--images-only')
    if mode == 'preview':
        cmd.append('--preview')
    if mode == 'scene':  # prévia de uma única cena, em 720p
        if not isinstance(scene, int) or isinstance(scene, bool) or scene < 1:
            raise JobError('Informe o número da cena (1 ou mais).')
        cmd.extend(['--scenes', f'{scene}-{scene}', '--res', '1280x720'])
    if provider:
        if provider not in PROVIDERS:
            raise JobError(f'Fornecedor inválido: {provider}')
        cmd.extend(['--image-provider', provider])
    regen = (regen or '').strip()
    if regen:
        if not _REGEN.fullmatch(regen):
            raise JobError('Use apenas números de cenas separados por vírgula, ex.: 1,3')
        cmd.extend(['--regen', regen])
    if strict:
        cmd.append('--strict-images')
    if no_voice and mode != 'images':
        cmd.append('--no-voice')
    if mode == 'preview':
        cmd.extend(['--output', 'output/preview.mp4'])
    if mode == 'scene':
        cmd.extend(['--output', f'output/cena_{scene:02}.mp4'])
    return cmd


def kill_tree(proc):
    """Encerra o processo e seus filhos (o ffmpeg sobreviveria a um simples terminate())."""
    if proc.poll() is not None:
        return
    if sys.platform == 'win32':
        try:
            subprocess.run(['taskkill', '/T', '/F', '/PID', str(proc.pid)], capture_output=True,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            return
        except OSError:
            pass
    proc.terminate()


class JobManager:
    """Só uma produção por vez: geram arquivos no mesmo canal e disputam CPU/API."""

    def __init__(self, install_dir):
        self.install_dir = Path(install_dir)
        self._lock = threading.Lock()
        self._job = None
        self._seq = 0

    def start(self, script, mode, channel, script_name, **opts):
        cmd = build_command(sys.executable, self.install_dir / 'main.py', script, mode, **opts)
        with self._lock:
            if self._job and self._job['status'] == 'running':
                raise JobError('Já existe uma produção em andamento.')
            self._seq += 1
            job = {'id': self._seq, 'mode': mode, 'channel': channel, 'script': script_name,
                   'status': 'running', 'returncode': None, 'lines': [], 'percent': 0.0,
                   'label': 'Iniciando…', 'started': time.time(), 'proc': None, 'cancelled': False,
                   '_total': 0, '_done': 0}
            self._job = job
        threading.Thread(target=self._run, args=(job, cmd), daemon=True).start()
        return job['id']

    def _run(self, job, cmd):
        env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
        try:
            proc = subprocess.Popen(cmd, cwd=str(self.install_dir), stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                                    errors='replace', bufsize=1, env=env,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except OSError as err:
            self._finish(job, -1, f'Não foi possível iniciar: {err}')
            return
        job['proc'] = proc
        if job['cancelled']:  # cancelado enquanto o processo ainda estava subindo
            kill_tree(proc)
        for raw in proc.stdout:
            self._on_line(job, raw.rstrip('\r\n'))
        self._finish(job, proc.wait())

    def _on_line(self, job, line):
        with self._lock:
            job['lines'].append(line)
            mode = job['mode']
            m = _RENDER_STEP.match(line)
            if m and mode != 'images':
                i, n = int(m.group(1)), int(m.group(2))
                job['percent'] = round((i - 1) / n * 0.9, 3)
                job['label'] = f'Cena {i} de {n}'
            elif line.startswith('Montando vídeo'):
                job['percent'], job['label'] = 0.93, 'Montando o vídeo final…'
            m = _IMAGES_TOTAL.match(line)
            if m:
                job['_total'] = int(m.group(1))
                job['label'] = f'Gerando {job["_total"]} imagem(ns)…'
            if _IMAGE_DONE.match(line) and job['_total']:
                job['_done'] += 1
                if mode == 'images':
                    job['percent'] = round(min(job['_done'] / job['_total'], 0.99), 3)
                    job['label'] = f'Imagem {job["_done"]} de {job["_total"]}'

    def _finish(self, job, code, message=None):
        with self._lock:
            if message:
                job['lines'].append(message)
            job['returncode'] = code
            job['ended'] = time.time()
            if job['cancelled']:
                job['status'], job['label'] = 'cancelled', 'Cancelado'
            elif code == 0:
                job['status'], job['percent'], job['label'] = 'done', 1.0, 'Concluído'
            else:
                job['status'], job['label'] = 'error', 'Terminou com erro'
            job['proc'] = None

    def cancel(self):
        with self._lock:
            job = self._job
            if not job or job['status'] != 'running':
                return False
            job['cancelled'] = True
            proc = job['proc']
        if proc is not None:
            kill_tree(proc)
        return True

    def snapshot(self, since=0):
        with self._lock:
            job = self._job
            if not job:
                return None
            return {'id': job['id'], 'mode': job['mode'], 'channel': job['channel'],
                    'script': job['script'], 'status': job['status'], 'returncode': job['returncode'],
                    'percent': job['percent'], 'label': job['label'],
                    'elapsed': round(job.get('ended', time.time()) - job['started'], 1),
                    'offset': len(job['lines']), 'lines': job['lines'][since:]}
