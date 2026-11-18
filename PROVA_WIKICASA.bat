@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Scout Immobili - prova Wikicasa
if not exist ".venv\Scripts\python.exe" (
  echo Prima esegui INSTALLA.bat
  pause
  exit /b 1
)
echo  ===== Prova Wikicasa tramite Apify (wikicasa.pagine in config, di solito 8 pagine = circa 200 annunci) =====
".venv\Scripts\python.exe" -m scout scrape --siti wikicasa_apify || goto errore
echo.
echo  ===== Analisi, Excel, mappa e pubblicazione sul sito =====
".venv\Scripts\python.exe" -m scout analizza --no-alert || goto errore
echo.
echo Fatto. Il registro completo e' in data\log\scout.log
pause
exit /b 0

:errore
echo.
echo ERRORE: manda le righe qui sopra a chi gestisce il bot.
pause
exit /b 1
