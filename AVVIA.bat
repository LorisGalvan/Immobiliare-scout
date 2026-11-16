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
echo  ===== 1/2 Raccolta annunci (lenta di proposito: 10-30 minuti) =====
".venv\Scripts\python.exe" -m scout scrape
echo.
echo  ===== 2/2 Analisi, Excel, mappa e pubblicazione sul sito =====
".venv\Scripts\python.exe" -m scout analizza
echo.
echo Fatto. Excel e mappa sono nella cartella "output". Il registro completo e' in data\log\scout.log
if /i not "%1"=="auto" pause
