@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Scout Immobili
if not exist ".venv\Scripts\python.exe" (
  echo Prima esegui INSTALLA.bat
  pause
  exit /b 1
)
findstr /c:"INCOLLA_QUI_LA_CHIAVE_SECRET" config.local.yaml >nul 2>&1 && (
  echo ATTENZIONE: in config.local.yaml manca ancora la chiave secret di Supabase.
  echo Senza chiave il bot funziona ma non pubblica sul sito.
  echo.
)
if not exist "pagine_salvate" mkdir "pagine_salvate"
echo  ===== 0/2 Pagine salvate dal browser (cartella pagine_salvate) =====
".venv\Scripts\python.exe" -m scout importa-html pagine_salvate --archivia || goto errore
echo.
echo  ===== 1/2 Raccolta annunci (lenta di proposito: 10-30 minuti) =====
".venv\Scripts\python.exe" -c "import numpy.random, pandas, shapely, lxml" 2>nul || goto bloccato
".venv\Scripts\python.exe" -m scout scrape || goto errore
echo.
echo  ===== 2/2 Analisi, Excel, mappa e pubblicazione sul sito =====
".venv\Scripts\python.exe" -m scout analizza || goto errore
echo.
echo Fatto. Excel e mappa sono nella cartella "output". Il registro completo e' in data\log\scout.log
if /i not "%1"=="auto" pause
exit /b 0

:bloccato
echo.
echo ERRORE: Windows blocca i file delle librerie Python ^(Controllo intelligente delle app^).
echo Vedi le istruzioni nel README, paragrafo "Windows blocca le librerie".
if /i not "%1"=="auto" pause
exit /b 2

:errore
echo.
echo ERRORE: l'esecuzione si e' interrotta. Manda le righe qui sopra a chi gestisce il bot.
if /i not "%1"=="auto" pause
exit /b 1
