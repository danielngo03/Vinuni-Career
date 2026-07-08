@echo off
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py -3 %*
  exit /b %ERRORLEVEL%
)

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  python %*
  exit /b %ERRORLEVEL%
)

where python3 >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  python3 %*
  exit /b %ERRORLEVEL%
)

echo AI log hook skipped: Python was not found on PATH. 1>&2
exit /b 0
