@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Scout Immobili - recupera esecuzione Apify
if not exist ".venv\Scripts\python.exe" (
  echo Prima esegui INSTALLA.bat
  pause
  exit /b 1
)
echo Recupera i risultati di un giro Apify gia' pagato (senza rifarlo e senza costi).
echo Il codice "run" e' nel messaggio "Apify: avviato ... (run XXXX)" oppure su console.apify.com, Runs.
echo.
set /p SCOUT_APIFY_RUN=Codice run: 
echo.
echo Fonte: 1 = Facebook   2 = Immobiliare   3 = Wikicasa   4 = Idealista   5 = Casa.it
set /p SCELTA=Scelta (da 1 a 5): 
set SITO=facebook_apify
if "%SCELTA%"=="2" set SITO=immobiliare_apify
if "%SCELTA%"=="3" set SITO=wikicasa_apify
if "%SCELTA%"=="4" set SITO=idealista_apify
if "%SCELTA%"=="5" set SITO=casa_apify
".venv\Scripts\python.exe" -m scout scrape --siti %SITO% || goto errore
set SCOUT_APIFY_RUN=
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
