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
echo Quale portale leggere?
echo   1 = Idealista e Casa.it
echo   2 = solo Idealista
echo   3 = solo Casa.it
set "SCELTA=1"
set /p "SCELTA=Numero (invio = 1): "
set "SITI=idealista_apify,casa_apify"
if "%SCELTA%"=="2" set "SITI=idealista_apify"
if "%SCELTA%"=="3" set "SITI=casa_apify"
echo  ===== %SITI% tramite Apify (fino a 3.000 annunci ciascuno, pochi dollari) =====
".venv\Scripts\python.exe" -m scout scrape --siti %SITI% --comuni verona || goto errore
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
