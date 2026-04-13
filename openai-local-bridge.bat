@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PS1=%SCRIPT_DIR%openai-local-bridge.ps1"

if not exist "%PS1%" (
  echo missing script: "%PS1%" 1>&2
  exit /b 1
)

set "POWERSHELL_EXE="
where pwsh >nul 2>nul
if %errorlevel%==0 set "POWERSHELL_EXE=pwsh"

if not defined POWERSHELL_EXE (
  where powershell >nul 2>nul
  if %errorlevel%==0 set "POWERSHELL_EXE=powershell"
)

if not defined POWERSHELL_EXE (
  echo missing command: pwsh or powershell 1>&2
  exit /b 1
)

"%POWERSHELL_EXE%" -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
exit /b %errorlevel%
