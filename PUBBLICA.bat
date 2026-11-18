@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Scout Immobili - pubblica sul sito
if not exist ".venv\Scripts\python.exe" (
  echo Prima esegui INSTALLA.bat
  pause
  exit /b 1
)
echo  ===== Ricalcolo e pubblicazione sul sito (senza nuove ricerche, senza alert) =====
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
