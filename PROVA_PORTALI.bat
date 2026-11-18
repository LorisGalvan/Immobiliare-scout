@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Scout Immobili - Idealista e Casa.it
if not exist ".venv\Scripts\python.exe" (
  echo Prima esegui INSTALLA.bat
  pause
  exit /b 1
)
echo  ===== Idealista e Casa.it tramite Apify (fino a 3.000 annunci ciascuno, circa 5 $ in tutto) =====
".venv\Scripts\python.exe" -m scout scrape --siti idealista_apify,casa_apify || goto errore
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
