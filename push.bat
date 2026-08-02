@echo off
:: Video Dubber Release & Push Script with Version Tagging & Release Notes
set PATH=%PATH%;C:\Program Files\Git\cmd

echo ========================================================
echo   Video Dubber - Release & Push Updates to GitHub
echo ========================================================
echo.

set /p TAG="Enter new version tag (e.g. v1.2.2 or press ENTER to skip tag): "
set /p NOTES="Enter Release Notes description: "

if "%NOTES%"=="" set NOTES=Performance enhancements and bug fixes

echo.
echo [1/4] Staging modified files...
git add .

echo.
echo [2/4] Committing changes with Release Notes...
git commit -m "%NOTES%"

echo.
echo [3/4] Pushing code to GitHub main branch...
git push origin main

if not "%TAG%"=="" (
    echo.
    echo [4/4] Creating version tag %TAG% for GitHub Release Notes...
    git tag -a %TAG% -m "%NOTES%"
    git push origin %TAG%
)

echo.
echo ========================================================
echo   SUCCESS! Release published to GitHub online.
echo ========================================================
pause
