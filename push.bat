@echo off
:: Video Dubber Easy Push Script for GitHub Online Updates
set PATH=%PATH%;C:\Program Files\Git\cmd

echo ========================================================
echo   Video Dubber - Push Updates to GitHub
echo ========================================================
echo.

set /p MSG="Enter commit message (or press ENTER for default 'Update'): "
if "%MSG%"=="" set MSG=Update project online

echo.
echo [1/3] Adding modified files...
git add .

echo.
echo [2/3] Committing changes: "%MSG%"
git commit -m "%MSG%"

echo.
echo [3/3] Pushing to GitHub main branch...
git push origin main

echo.
echo ========================================================
echo   SUCCESS! Project updated on GitHub online.
echo ========================================================
pause
