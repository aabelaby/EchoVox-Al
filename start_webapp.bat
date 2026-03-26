@echo off
echo =======================================
echo   Starting EchoVox Web App (Flask)
echo =======================================
echo.

:: ── Activate Anaconda so all DLLs and packages are on PATH ──
call D:\anaconda\Scripts\activate.bat D:\anaconda

:: ── Environment fixes (persist for this process tree) ──
set KMP_DUPLICATE_LIB_OK=TRUE
set OMP_NUM_THREADS=1

cd /d D:\Echovox_fullcode

echo Starting Flask server...
echo Open http://localhost:5000 in your browser
echo.
python app.py

:: If it exits (error or Ctrl+C), keep window open so user can read output
echo.
echo Server stopped. Press any key to close...
pause >nul
