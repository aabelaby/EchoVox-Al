@echo off
echo =======================================
echo   Starting EchoVox Web App (Flask)
echo =======================================
echo.

:: ── Environment fixes (persist for this process tree) ──
set KMP_DUPLICATE_LIB_OK=TRUE
set OMP_NUM_THREADS=1

:: ── Try to activate conda if available ──
where conda >nul 2>&1
if %ERRORLEVEL%==0 (
    call conda activate base
) else (
    :: Common Anaconda locations — edit if yours differs
    if exist "%USERPROFILE%\anaconda3\Scripts\activate.bat" (
        call "%USERPROFILE%\anaconda3\Scripts\activate.bat" "%USERPROFILE%\anaconda3"
    ) else if exist "%USERPROFILE%\miniconda3\Scripts\activate.bat" (
        call "%USERPROFILE%\miniconda3\Scripts\activate.bat" "%USERPROFILE%\miniconda3"
    ) else if exist "D:\anaconda\Scripts\activate.bat" (
        call "D:\anaconda\Scripts\activate.bat" "D:\anaconda"
    )
)

:: ── Change to the project directory (same folder as this .bat) ──
cd /d "%~dp0"

echo Starting Flask server...
echo Open http://localhost:5000 in your browser
echo.
python app.py

:: If it exits (error or Ctrl+C), keep window open so user can read output
echo.
echo Server stopped. Press any key to close...
pause >nul
