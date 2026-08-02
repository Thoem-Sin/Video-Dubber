# Video Dubber PowerShell Release & Push Script
$env:Path += ";C:\Program Files\Git\cmd"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  Video Dubber - Release & Push Updates to GitHub" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

$tag = Read-Host "Enter new version tag (e.g. v1.2.2 or press ENTER to skip tag)"

# Read multi-line Release Notes from RELEASE_NOTES.txt if available
if (Test-Path "RELEASE_NOTES.txt") {
    $notes = Get-Content "RELEASE_NOTES.txt" -Raw
    Write-Host "[INFO] Loaded Release Notes from RELEASE_NOTES.txt" -ForegroundColor Green
} else {
    $notes = Read-Host "Enter short Release Notes summary"
}

if ([string]::IsNullOrWhiteSpace($notes)) {
    $notes = "Performance enhancements and bug fixes"
}

if ($tag) { $tag = ($tag -replace '[\r\n]', '').Trim() }

Write-Host "`n[1/4] Staging modified files..." -ForegroundColor Yellow
git add .

Write-Host "[2/4] Committing changes..." -ForegroundColor Yellow
git commit -m "$notes"

Write-Host "[3/4] Pushing code to GitHub main branch..." -ForegroundColor Yellow
git push origin main

if (-not [string]::IsNullOrWhiteSpace($tag)) {
    Write-Host "[4/4] Creating version tag $tag for GitHub Release Notes..." -ForegroundColor Yellow
    git tag -a $tag -m "$notes"
    git push origin $tag
} else {
    Write-Host "`n[INFO] No version tag entered. Code pushed to main (skipping GitHub Release tag)." -ForegroundColor Cyan
}

Write-Host "`n========================================================" -ForegroundColor Green
Write-Host "  SUCCESS! Code pushed to GitHub online." -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green

