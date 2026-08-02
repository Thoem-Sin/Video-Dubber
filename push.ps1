# Video Dubber PowerShell Push Script for GitHub Online Updates
$env:Path += ";C:\Program Files\Git\cmd"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  Video Dubber - Push Updates to GitHub" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

$msg = Read-Host "Enter commit message (or press ENTER for default 'Update')"
if ([string]::IsNullOrWhiteSpace($msg)) {
    $msg = "Update project online"
}

Write-Host "`n[1/3] Adding modified files..." -ForegroundColor Yellow
git add .

Write-Host "[2/3] Committing changes..." -ForegroundColor Yellow
git commit -m "$msg"

Write-Host "[3/3] Pushing to GitHub main branch..." -ForegroundColor Yellow
git push origin main

Write-Host "`n========================================================" -ForegroundColor Green
Write-Host "  SUCCESS! Project updated on GitHub online." -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green
