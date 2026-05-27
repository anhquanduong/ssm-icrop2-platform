@echo off
rem ══════════════════════════════════════════════════════════════
rem  SSM-iCrop 2 — Production Launch Script
rem  Machine-isolated virtual environment to prevent OneDrive sync conflicts.
rem ══════════════════════════════════════════════════════════════

set VENV_DIR=env_%COMPUTERNAME%
set PYTHON_CMD=

rem 1. Check if global python is functional (ignore Microsoft Store dummy alias)
where python >nul 2>nul
if %errorlevel% equ 0 (
    for /f "tokens=*" %%i in ('where python 2^>nul') do (
        echo %%i | findstr /i "WindowsApps" >nul
        if errorlevel 1 (
            set PYTHON_CMD="%%i"
            goto :PYTHON_FOUND
        )
    )
)

rem 2. Check for local uv-managed Python
if exist "C:\Users\%USERNAME%\AppData\Roaming\uv\python" (
    for /d %%d in ("C:\Users\%USERNAME%\AppData\Roaming\uv\python\*") do (
        if exist "%%d\python.exe" (
            set PYTHON_CMD="%%d\python.exe"
            goto :PYTHON_FOUND
        )
    )
)

rem 3. Check for standard local user Python
if exist "C:\Users\%USERNAME%\AppData\Local\Programs\Python" (
    for /d %%d in ("C:\Users\%USERNAME%\AppData\Local\Programs\Python\*") do (
        if exist "%%d\python.exe" (
            set PYTHON_CMD="%%d\python.exe"
            goto :PYTHON_FOUND
        )
    )
)

rem 4. Check for Anaconda
if exist "C:\ProgramData\anaconda3\python.exe" (
    set PYTHON_CMD="C:\ProgramData\anaconda3\python.exe"
    goto :PYTHON_FOUND
)
if exist "C:\Users\%USERNAME%\anaconda3\python.exe" (
    set PYTHON_CMD="C:\Users\%USERNAME%\anaconda3\python.exe"
    goto :PYTHON_FOUND
)

echo Error: Python was not found. Install Python 3.x from python.org.
pause
exit /b 1

:PYTHON_FOUND
echo Python resolved: %PYTHON_CMD%

if not exist %VENV_DIR%\Scripts\activate (
    echo Initializing machine-isolated environment: %VENV_DIR%
    %PYTHON_CMD% -m venv %VENV_DIR%
    call %VENV_DIR%\Scripts\pip install -q --upgrade pip
    call %VENV_DIR%\Scripts\pip install -q -r requirements.txt
)

call %VENV_DIR%\Scripts\activate
echo SSM-iCrop 2 Environment Ready. Launching dashboard...
streamlit run ui.py
pause
