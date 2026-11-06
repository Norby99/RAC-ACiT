@echo off
setlocal

rem ============================================================
rem  LINGUA DEL GIOCO: cambia solo il valore dopo "LINGUA="
rem    it = italiano     en = inglese     fr = francese
rem    es = spagnolo     de = tedesco     nl = olandese
rem ============================================================
set "LINGUA=it"


rem Da qui in poi non serve modificare nulla.
set "ROOT=%~dp0"
set "ROOT=%ROOT:\=/%"
set "ESEGUIBILE=%~dp0game\build-win\game\RaCACiT.exe"

if not exist "%ESEGUIBILE%" (
    echo Gioco non trovato: %ESEGUIBILE%
    echo Va prima compilato.
    pause
    exit /b 1
)
if not exist "%~dp0dev\EBOOT.ELF" (
    echo File non trovato: %~dp0dev\EBOOT.ELF
    pause
    exit /b 1
)

if not exist "%~dp0analysis\run\hdd0" mkdir "%~dp0analysis\run\hdd0"
if not exist "%~dp0analysis\run\hdd1" mkdir "%~dp0analysis\run\hdd1"

set "PS3_VFS_ROOT=%ROOT%dev/BCES00511"
set "PS3_HDD0_ROOT=%ROOT%analysis/run/hdd0"
set "PS3_HDD1_ROOT=%ROOT%analysis/run/hdd1"
set "RACACIT_LOG_FILE=%ROOT%analysis/run/game.log"
set "RACACIT_LANGUAGE=%LINGUA%"

cd /d "%~dp0analysis\run"
"%ESEGUIBILE%" "%ROOT%dev/EBOOT.ELF"

if errorlevel 1 (
    echo.
    echo Il gioco si e' chiuso con un errore. Log: analysis\run\game.log
    pause
)
