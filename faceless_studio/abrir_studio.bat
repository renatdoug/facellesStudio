@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Faceless Studio ainda nao foi instalado.
    echo Execute setup.bat primeiro.
    pause
    exit /b 1
)
echo Abrindo o Faceless Studio no navegador...
echo Mantenha esta janela aberta enquanto usa o programa. Feche-a para encerrar.
".venv\Scripts\python.exe" web.py
if errorlevel 1 pause
