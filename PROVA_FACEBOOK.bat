@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Scout Immobili - prova Facebook
if not exist ".venv\Scripts\python.exe" (
  echo Prima esegui INSTALLA.bat
  pause
  exit /b 1
)
echo  ===== Prova Facebook Marketplace tramite Apify (facebook.max_annunci in config, di solito 100) =====
".venv\Scripts\python.exe" -m scout scrape --siti facebook_apify || goto errore
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
