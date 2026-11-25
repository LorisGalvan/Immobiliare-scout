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
echo  ===== Wikicasa tramite Apify (wikicasa.pagine in config: 30 pagine = tutta Verona, circa 4 $) =====
".venv\Scripts\python.exe" -m scout scrape --siti wikicasa_apify --comuni verona || goto errore
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
