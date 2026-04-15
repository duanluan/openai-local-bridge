@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PS1=%SCRIPT_DIR%openai-local-bridge.ps1"
set "LANGUAGE_RAW=%OLB_LANG%"
if not defined LANGUAGE_RAW set "LANGUAGE_RAW=%LANG%"
set "APP_LANG=en"
if /I "%LANGUAGE_RAW:~0,2%"=="zh" set "APP_LANG=zh"

if not exist "%PS1%" (
  if /I "%APP_LANG%"=="zh" (
    echo 缺少脚本: "%PS1%" 1^>^&2
  ) else (
    echo missing script: "%PS1%" 1^>^&2
  )
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
  if /I "%APP_LANG%"=="zh" (
    echo 缺少命令: pwsh 或 powershell 1^>^&2
  ) else (
    echo missing command: pwsh or powershell 1^>^&2
  )
  exit /b 1
)

"%POWERSHELL_EXE%" -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
exit /b %errorlevel%
