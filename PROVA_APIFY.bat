@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Scout Immobili - prova Apify
if not exist ".venv\Scripts\python.exe" (
  echo Prima esegui INSTALLA.bat
  pause
  exit /b 1
)
echo  ===== Prova Immobiliare tramite Apify (apify.max_annunci in config, di solito 200) =====
".venv\Scripts\python.exe" -m scout scrape --siti immobiliare_apify --comuni verona || goto errore
echo.
echo  ===== Analisi, Excel, mappa e pubblicazione sul sito =====
".venv\Scripts\python.exe" -m scout analizza || goto errore
echo.
echo Fatto. Il registro completo e' in data\log\scout.log
pause
exit /b 0

:errore
echo.
echo ERRORE: manda le righe qui sopra a chi gestisce il bot.
pause
exit /b 1
