#!/usr/bin/env python3
"""Faceless Studio — abre a interface web local no navegador.

    python web.py              # http://127.0.0.1:8765
    python web.py --no-browser
"""
import argparse
import json
import socket
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CHANNELS = ROOT.parent / 'canais'


def port_free(port):
    """True se ninguém está escutando em 127.0.0.1:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('127.0.0.1', port))
        except OSError:
            return False
    return True


def find_free_port(start, tries=30):
    return next((p for p in range(start, start + tries) if port_free(p)), None)


def faceless_info(port):
    """Se a porta for de uma instância do Faceless Studio, devolve o /api/meta dela (dict);
    senão None. Instâncias antigas não informam versão."""
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/meta', timeout=1.5) as r:
            data = json.loads(r.read().decode('utf-8'))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and 'providers' in data else None


def main():
    p = argparse.ArgumentParser(description='Interface web do Faceless Studio')
    p.add_argument('--port', type=int, default=8765)
    p.add_argument('--no-browser', action='store_true')
    p.add_argument('--channels', default=str(CHANNELS), help='Pasta com os canais (padrão: ../canais)')
    args = p.parse_args()
    try:
        import uvicorn
        from studio import __version__
        from webui.app import create_app
    except ImportError as err:
        sys.exit(f'Dependência ausente ({err}). Rode setup.bat (ou: pip install -r requirements.txt).')

    port = args.port
    if not port_free(port):
        info = faceless_info(port)
        if info is not None and info.get('version') == __version__:
            url = f'http://127.0.0.1:{port}'
            print(f'O Faceless Studio {__version__} já está aberto em {url}. Abrindo no navegador.', flush=True)
            if not args.no_browser:
                webbrowser.open(url)
            return
        new = find_free_port(port + 1)
        if new is None:
            sys.exit(f'A porta {port} está ocupada e não achei outra livre. Feche outras janelas do Faceless Studio.')
        if info is not None:
            print(f'Há outra janela do Faceless Studio (versão {info.get("version", "antiga")}) aberta na porta {port}. '
                  f'Feche-a quando puder; esta usa a porta {new}.', flush=True)
        else:
            print(f'A porta {port} está ocupada por outro programa; usando a porta {new}.', flush=True)
        port = new

    channels = Path(args.channels).resolve()
    channels.mkdir(parents=True, exist_ok=True)
    app = create_app(channels, ROOT)
    url = f'http://127.0.0.1:{port}'
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print(f'Faceless Studio {__version__} em {url}  (Ctrl+C para encerrar)', flush=True)
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning')


if __name__ == '__main__':
    main()
