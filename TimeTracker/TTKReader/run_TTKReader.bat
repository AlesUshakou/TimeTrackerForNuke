@echo off
setlocal

set PYTHON=python


%PYTHON% -c "import PySide6" >nul 2>&1
if %errorlevel%==0 (
    echo PySide6 found.
    goto run_script
)


%PYTHON% -c "import PySide2" >nul 2>&1
if %errorlevel%==0 (
    echo PySide2 found.
    goto run_script
)

echo.
echo =========================================
echo ERROR: PySide6 or PySide2 is not installed.
echo Install PySide6 before running TimeTracker.
echo =========================================
echo.
pause
exit /b 1

:run_script
echo Launching TimeTracker...
%PYTHON% "TTKReader.py"

endlocal