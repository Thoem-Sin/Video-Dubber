import urllib.request, re, json

GITHUB_REPO = "thoem-sin/video-dubber"

print("=== Testing update check methods ===\n")

# Method 1: releases/latest API
print("[Method 1] GitHub Releases API...")
try:
    req = urllib.request.Request(
        f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
        headers={"User-Agent": "VideoDubberStudio-App/1.2"}
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        data = json.loads(r.read())
    print(f"  SUCCESS: tag={data.get('tag_name')}")
except Exception as e:
    print(f"  FAILED: {e}")

# Method 2: tags API
print("[Method 2] GitHub Tags API...")
try:
    req = urllib.request.Request(
        f"https://api.github.com/repos/{GITHUB_REPO}/tags",
        headers={"User-Agent": "VideoDubberStudio-App/1.2"}
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        data = json.loads(r.read())
    print(f"  SUCCESS: tags={[t['name'] for t in data]}")
except Exception as e:
    print(f"  FAILED: {e}")

# Method 3: Raw git refs (no rate limit)
print("[Method 3] Raw git refs (no rate limit)...")
try:
    req = urllib.request.Request(
        f"https://github.com/{GITHUB_REPO}.git/info/refs?service=git-upload-pack",
        headers={"User-Agent": "git/2.0"}
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        content = r.read().decode("utf-8", errors="ignore")
    tags = re.findall(r"refs/tags/(v[\d]+\.[\d]+\.[\d]+)", content)
    unique_tags = sorted(set(tags), key=lambda t: [int(x) for x in t.lstrip("v").split(".")])
    print(f"  SUCCESS: tags={unique_tags}")
    if unique_tags:
        latest = unique_tags[-1]
        print(f"  Latest: {latest}")
except Exception as e:
    print(f"  FAILED: {e}")

# Test live app endpoint
print("\n[Live App] /api/check_update response...")
try:
    with urllib.request.urlopen("http://127.0.0.1:5000/api/check_update", timeout=5) as r:
        data = json.loads(r.read())
    print(json.dumps(data, indent=2))
except Exception as e:
    print(f"  FAILED: {e}")
