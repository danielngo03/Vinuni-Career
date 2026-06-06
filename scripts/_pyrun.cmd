@echo off
REM Cross-platform Python launcher for AI log hooks (Windows cmd.exe).
REM Tries python -> python3 -> Codex bundled Python -> py -3 in order,
REM runs the given script with all args.
REM Exits 0 silently if no Python is found - hooks must never block the AI tool.

where python >nul 2>nul
if %ERRORLEVEL%==0 (
  python %*
  exit /b %ERRORLEVEL%
)

where python3 >nul 2>nul
if %ERRORLEVEL%==0 (
  python3 %*
  exit /b %ERRORLEVEL%
)

set "CODEX_BUNDLED_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%CODEX_BUNDLED_PY%" (
  "%CODEX_BUNDLED_PY%" %*
  exit /b %ERRORLEVEL%
)

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 %*
  exit /b %ERRORLEVEL%
)

exit /b 0
