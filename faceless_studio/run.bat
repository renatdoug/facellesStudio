@echo off
REM Gera o video a partir de um roteiro. Rode setup.bat uma vez antes deste arquivo.
REM Uso:  run.bat                    -> usa roteiro_uti.json
REM       run.bat meu_roteiro.json   -> usa outro roteiro
REM Para opcoes mais especificas (--preview, --voice, --music...), use diretamente:
REM       .venv\Scripts\activate  &&  python main.py --script meu_roteiro.json --preview
cd /d "%~dp0"

if not exist .venv (
    echo Ambiente nao preparado ainda. Rode setup.bat primeiro.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

set SCRIPT=roteiro_uti.json
if not "%~1"=="" set SCRIPT=%~1

echo.
echo ===== Passo 1 de 2: gerando e revisando as imagens =====
python main.py --script "%SCRIPT%" --images-only
if errorlevel 1 goto fim

echo.
echo Confira as imagens na "Folha de revisao" indicada acima (revisao_imagens.jpg).
echo Para trocar uma: edite o roteiro (prompt ou image) e rode de novo,
echo ou use: python main.py --script "%SCRIPT%" --images-only --regen NUMERO_DA_CENA
echo.
set /p CONTINUAR="Continuar e gerar o video completo agora? (s/n) "
if /i not "%CONTINUAR%"=="s" goto fim

echo.
echo ===== Passo 2 de 2: gerando o video =====
python main.py --script "%SCRIPT%"

:fim
pause
