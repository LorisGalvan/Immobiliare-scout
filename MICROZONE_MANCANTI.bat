@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Scout Immobili - microzone mancanti
if not exist ".venv\Scripts\python.exe" (
  echo Prima esegui INSTALLA.bat
  pause
  exit /b 1
)
echo  ===== Disegno le microzone dove le tue non arrivano (da OpenStreetMap: strade principali, fiumi, ferrovie) =====
echo  Le tue 50 zone restano come sono. Copia di sicurezza: data\zone\verona.backup.geojson
".venv\Scripts\python.exe" -m scout zone-auto --solo-scoperto --livello medio || goto errore
echo.
echo  ===== Ricalcolo e pubblicazione sul sito =====
".venv\Scripts\python.exe" -m scout analizza --no-alert || goto errore
echo.
echo Fatto. Controlla le nuove zone sul sito (Mappa e Microzone).
echo Se non ti piacciono, ANNULLA_MICROZONE.bat rimette le tue 50 zone.
pause
exit /b 0

:errore
echo.
echo ERRORE: manda le righe qui sopra a chi gestisce il bot.
pause
exit /b 1
