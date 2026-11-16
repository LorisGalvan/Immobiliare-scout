@echo off
REM Esecuzione giornaliera - da Utilita di pianificazione di Windows
REM Modifica il percorso qui sotto
cd /d "C:\scout_immobili"
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
python -m scout run
REM python -m scout -c config_sgl.yaml run
