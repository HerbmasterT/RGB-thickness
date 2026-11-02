@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" optical_contrast\optical_contrast_inspector.py
    goto :done
)
where py >nul 2>nul
if not errorlevel 1 (
    py -3 optical_contrast\optical_contrast_inspector.py
    goto :done
)
if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
    "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" optical_contrast\optical_contrast_inspector.py
    goto :done
)
python optical_contrast\optical_contrast_inspector.py
:done
if errorlevel 1 (
    echo.
    echo Failed to start. See README.md for Python and Pillow installation.
    pause
)
endlocal
