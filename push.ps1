# Video Dubber PowerShell Release & Push Script
$env:Path += ";C:\Program Files\Git\cmd"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  Video Dubber - Release & Push Updates to GitHub" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

$tag = Read-Host "Enter new version tag (e.g. v1.2.2 or press ENTER to skip tag)"
$notes = Read-Host "Enter Release Notes description"

if ([string]::IsNullOrWhiteSpace($notes)) {
    $notes = "Performance enhancements and bug fixes"
}

Write-Host "`n[1/4] Staging modified files..." -ForegroundColor Yellow
git add .

Write-Host "[2/4] Committing changes with Release Notes..." -ForegroundColor Yellow
git commit -m "$notes"

Write-Host "[3/4] Pushing code to GitHub main branch..." -ForegroundColor Yellow
git push origin main

if (-not [string]::IsNullOrWhiteSpace($tag)) {
    Write-Host "[4/4] Creating version tag $tag for GitHub Release Notes..." -ForegroundColor Yellow
    git tag -a $tag -m "$notes"
    git push origin $tag
}

Write-Host "`n========================================================" -ForegroundColor Green
Write-Host "  SUCCESS! Release published to GitHub online." -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green
