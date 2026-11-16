@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Scout Immobili - installazione
echo.
echo  ===== SCOUT IMMOBILI - INSTALLAZIONE =====
echo.

rem --- 1. Python -----------------------------------------------------------
set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (
  python --version >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo Python non trovato: provo a installarlo con winget...
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  echo.
  echo Se l'installazione e' andata a buon fine CHIUDI questa finestra e fai di nuovo doppio clic su INSTALLA.bat.
  echo Se invece da' errore, scarica Python da https://www.python.org/downloads/
  echo e durante l'installazione spunta "Add python.exe to PATH".
  pause
  exit /b 1
)
echo Python trovato:
%PY% --version

rem --- 2. Ambiente e librerie ------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
  echo Creo l'ambiente Python...
  %PY% -m venv .venv || (echo ERRORE nella creazione dell'ambiente & pause & exit /b 1)
)
echo Installo le librerie (qualche minuto)...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt || (echo ERRORE nell'installazione delle librerie & pause & exit /b 1)

rem --- 3. Impostazioni personali ---------------------------------------------
if not exist "config.local.yaml" (
  > config.local.yaml echo # Impostazioni personali: questo file NON va su GitHub.
  >> config.local.yaml echo # Incolla tra le virgolette la chiave SECRET di Supabase:
  >> config.local.yaml echo # Supabase - Project Settings - API Keys - Secret keys
  >> config.local.yaml echo supabase:
  >> config.local.yaml echo   attivo: true
  >> config.local.yaml echo   service_key: "INCOLLA_QUI_LA_CHIAVE_SECRET"
  echo.
  echo Ora si apre il Blocco note: incolla la chiave SECRET al posto di INCOLLA_QUI_LA_CHIAVE_SECRET,
  echo poi salva ^(Ctrl+S^) e chiudi il Blocco note.
  pause
  notepad config.local.yaml
)

echo.
echo  ===== INSTALLAZIONE COMPLETATA =====
echo  Ora fai doppio clic su AVVIA.bat per scaricare gli annunci e pubblicarli sul sito.
echo.
pause
