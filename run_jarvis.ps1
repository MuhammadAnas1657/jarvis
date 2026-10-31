# Jarvis Startup Script for Windows
$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir
$env:PYTHONPATH = $ProjectDir

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "       JARVIS OFFLINE VOICE ENGINE        " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 1. Check Ollama (optional prompt if not running)
$ollamaRunning = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
if (-not $ollamaRunning) {
    Write-Host "[!] Note: Ollama process not detected. Jarvis will run in zero-cloud heuristic fallback mode." -ForegroundColor Yellow
} else {
    Write-Host "[+] Ollama service is active." -ForegroundColor Green
}

# 2. Check Database and Directories
if (-not (Test-Path "$ProjectDir\inbox")) {
    New-Item -ItemType Directory -Path "$ProjectDir\inbox" | Out-Null
}
if (-not (Test-Path "$ProjectDir\data")) {
    New-Item -ItemType Directory -Path "$ProjectDir\data" | Out-Null
}

# 3. Trigger morning briefing at startup
Write-Host "[*] Speaking morning briefing..." -ForegroundColor Cyan
python -m jarvis.main briefing

# 4. Launch background inbox watcher and Web Control Center
Write-Host "[*] Launching Jarvis Web Control Center on http://127.0.0.1:8000 ..." -ForegroundColor Green
python -m jarvis.main run --host 127.0.0.1 --port 8000

