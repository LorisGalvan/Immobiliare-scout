@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Scout Immobili - annulla microzone automatiche
if not exist "data\zone\verona.backup.geojson" (
  echo Nessuna copia di sicurezza trovata: niente da annullare.
  pause
  exit /b 1
)
copy /y "data\zone\verona.backup.geojson" "data\zone\verona.geojson" >/dev/null || goto errore
echo Rimesse le microzone precedenti. Ricalcolo e pubblico sul sito...
".venv\Scripts\python.exe" -m scout analizza --no-alert || goto errore
echo Fatto.
pause
exit /b 0

:errore
echo.
echo ERRORE: manda le righe qui sopra a chi gestisce il bot.
pause
exit /b 1
