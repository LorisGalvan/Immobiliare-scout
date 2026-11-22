@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Scout Immobili - carica l'archivio online
if not exist ".venv\Scripts\python.exe" (
  echo Prima esegui INSTALLA.bat
  pause
  exit /b 1
)
echo  ===== Carico l'archivio di questo PC nello spazio privato di Supabase =====
echo  Da fare UNA VOLTA SOLA. Dopo, i .bat e GitHub usano tutti la stessa copia online.
echo.
if /i "%1"=="forza" (
  ".venv\Scripts\python.exe" -m scout archivio-carica --forza || goto errore
) else (
  ".venv\Scripts\python.exe" -m scout archivio-carica || goto errore
)
echo.
pause
exit /b 0

:errore
echo.
echo ERRORE: manda le righe qui sopra a chi gestisce il bot.
pause
exit /b 1
