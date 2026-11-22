@echo off
REM Prepara o Faceless Studio no Windows: cria o ambiente virtual e instala as dependencias.
REM Depois de rodar este arquivo uma vez, use run.bat para gerar os videos.
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python nao encontrado. Instale o Python 3.10+ em https://www.python.org/downloads/
    echo e marque a opcao "Add python.exe to PATH" durante a instalacao.
    pause
    exit /b 1
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo FFmpeg nao encontrado no PATH.
    echo Baixe a build "essentials" em https://www.gyan.dev/ffmpeg/builds/, extraia e adicione
    echo a pasta "bin" dela as Variaveis de Ambiente do Windows ^(PATH^).
    pause
    exit /b 1
)

if not exist .venv (
    echo Criando o ambiente virtual...
    python -m venv .venv
)

call .venv\Scripts\activate.bat
echo Instalando as dependencias...
pip install --upgrade pip >nul
pip install -r requirements.txt

if not exist .env (
    copy .env.exemplo .env >nul
    echo Criado o arquivo .env - edite-o se for usar OpenAI ou Gemini para gerar imagens.
)

echo.
echo Tudo pronto! Use run.bat para gerar um video.
pause
