# Video Dubber PowerShell Release & Push Script
$env:Path += ";C:\Program Files\Git\cmd"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  Video Dubber - Release & Push Updates to GitHub" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

$tag = Read-Host "Enter new version tag (e.g. v1.2.2 or press ENTER to skip tag)"

# Prompt for Release Notes summary
$notes = Read-Host "Enter short Release Notes summary (or press ENTER for default)"

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
    Write-Host "[4/4] Creating version tag $tag and publishing GitHub Release..." -ForegroundColor Yellow
    git tag -f -a $tag -m "$notes"
    git push origin $tag --force
    
    # Auto-publish GitHub Release via API
    python -c "import urllib.request, json, subprocess; p = subprocess.Popen(['git', 'credential', 'fill'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True); out, _ = p.communicate('url=https://github.com/Thoem-Sin/Video-Dubber.git\n\n'); creds = dict(line.split('=', 1) for line in out.strip().split('\n') if '=' in line); token = creds.get('password'); headers = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github+json', 'User-Agent': 'VideoDubber-ReleaseBot'}; data = json.dumps({'tag_name': '$tag', 'name': 'Software Update', 'body': '$notes', 'draft': False, 'prerelease': False}).encode('utf-8'); req = urllib.request.Request('https://api.github.com/repos/Thoem-Sin/Video-Dubber/releases', data=data, headers=headers, method='POST'); res = urllib.request.urlopen(req); print('Published Release:', res.status)"
} else {
    Write-Host "`n[INFO] No version tag entered. Code pushed to main (skipping GitHub Release tag)." -ForegroundColor Cyan
}

Write-Host "`n========================================================" -ForegroundColor Green
Write-Host "  SUCCESS! Code pushed to GitHub online." -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green

