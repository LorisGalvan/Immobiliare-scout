@echo off
REM Esecuzione giornaliera: Utilita' di pianificazione di Windows -> Crea attivita' di base
REM -> Avvia programma: questo file. Nessun percorso da modificare.
call "%~dp0..\AVVIA.bat" auto >> "%~dp0..\data\log\giornaliero.log" 2>&1
