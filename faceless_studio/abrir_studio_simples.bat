@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Faceless Studio ainda nao foi instalado.
    echo Execute setup.bat primeiro.
    pause
    exit /b 1
)
start "Faceless Studio" ".venv\Scripts\pythonw.exe" "%~dp0gui.py"
