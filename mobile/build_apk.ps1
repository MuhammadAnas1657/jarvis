<#
.SYNOPSIS
  1-Command Android APK Builder for Jarvis 24/7 Buddy (Capacitor JS + Offline-First Engine)
.DESCRIPTION
  1. Copies the latest static/ frontend assets into mobile/www/ (preserving index.html & mobile-bridge.js)
  2. Installs Capacitor dependencies via npm install
  3. Initializes / syncs the Capacitor Android project (npx cap sync android)
  4. Compiles the standalone APK via .\android\gradlew.bat assembleDebug -> app-debug.apk
#>

$ErrorActionPreference = "Stop"
$MobileDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $MobileDir
$StaticDir = Join-Path $RootDir "static"
$WwwDir = Join-Path $MobileDir "www"
$WwwStaticDir = Join-Path $WwwDir "static"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " JARVIS 24/7 Buddy - Standalone Android APK Builder" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Ensure www and www/static directories exist and sync static assets
if (-not (Test-Path $WwwDir)) {
    New-Item -ItemType Directory -Path $WwwDir | Out-Null
}
if (-not (Test-Path $WwwStaticDir)) {
    New-Item -ItemType Directory -Path $WwwStaticDir | Out-Null
}

if (Test-Path $StaticDir) {
    Write-Host "[1/4] Copying latest static/ assets into mobile/www/..." -ForegroundColor Yellow
    Get-ChildItem -Path $StaticDir -File | ForEach-Object {
        if ($_.Name -ne "index.html" -and $_.Name -ne "mobile-bridge.js") {
            Copy-Item -Path $_.FullName -Destination (Join-Path $WwwDir $_.Name) -Force
            Copy-Item -Path $_.FullName -Destination (Join-Path $WwwStaticDir $_.Name) -Force
        }
    }
} else {
    Write-Host "[1/4] Using standalone mobile/www/ bundle..." -ForegroundColor Yellow
}

Set-Location $MobileDir

# 2. Install npm packages
Write-Host "[2/4] Running npm install..." -ForegroundColor Yellow
npm install

# 3. Add Android platform if not yet added, then sync Capacitor
$AndroidDir = Join-Path $MobileDir "android"
if (-not (Test-Path $AndroidDir)) {
    Write-Host "[3/4] Initializing Capacitor Android platform..." -ForegroundColor Yellow
    npx cap add android
}
Write-Host "[3/4] Syncing web assets to Capacitor Android project (npx cap sync android)..." -ForegroundColor Yellow
npx cap sync android

# 4. Build Debug APK via Gradle wrapper
$GradlewPath = Join-Path $AndroidDir "gradlew.bat"
if (Test-Path $GradlewPath) {
    Write-Host "[4/4] Building Android APK via .\android\gradlew.bat assembleDebug..." -ForegroundColor Yellow
    Push-Location $AndroidDir
    try {
        .\gradlew.bat assembleDebug
    } finally {
        Pop-Location
    }

    $ApkOutput = Join-Path $AndroidDir "app\build\outputs\apk\debug\app-debug.apk"
    $FriendlyApk = Join-Path $MobileDir "app-debug.apk"
    if (Test-Path $ApkOutput) {
        Copy-Item -Path $ApkOutput -Destination $FriendlyApk -Force
        Write-Host ""
        Write-Host "SUCCESS! Standalone APK built at:" -ForegroundColor Green
        Write-Host "  -> $FriendlyApk" -ForegroundColor Green
        Write-Host "  -> $ApkOutput" -ForegroundColor Green
    }
} else {
    Write-Host "[4/4] Android Gradle wrapper not found yet. Open in Android Studio with: npm run open:android" -ForegroundColor Yellow
}
