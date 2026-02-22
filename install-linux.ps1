# Installs WSL (Windows Subsystem for Linux) with Ubuntu.
# Usage: powershell -ExecutionPolicy Bypass -File install-linux.ps1
#
# FIRST: Go to Settings > System > For Developers > turn on "Developer Mode"
# Then run this script.

Write-Host ""
Write-Host "=== WSL (Linux) Installer ===" -ForegroundColor Cyan
Write-Host ""

# Check if WSL is already installed
$wslCheck = Get-Command wsl -ErrorAction SilentlyContinue
if ($wslCheck) {
    $installed = wsl --list --quiet 2>&1
    if ($installed -match "Ubuntu") {
        Write-Host "Ubuntu is already installed! Launch it by typing: wsl" -ForegroundColor Green
        Write-Host ""
        exit 0
    }
}

Write-Host "Step 1: Enabling Developer Mode check..." -ForegroundColor Yellow
$devMode = (Get-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock" -ErrorAction SilentlyContinue).AllowDevelopmentWithoutDevLicense
if ($devMode -ne 1) {
    Write-Host ""
    Write-Host "Developer Mode is NOT enabled yet." -ForegroundColor Red
    Write-Host "Please do this first:" -ForegroundColor Yellow
    Write-Host "  1. Open Settings (Win + I)" -ForegroundColor White
    Write-Host "  2. Go to: System > For Developers" -ForegroundColor White
    Write-Host "  3. Turn ON 'Developer Mode'" -ForegroundColor White
    Write-Host "  4. Re-run this script" -ForegroundColor White
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "Developer Mode is ON" -ForegroundColor Green

Write-Host ""
Write-Host "Step 2: Installing WSL with Ubuntu..." -ForegroundColor Yellow
Write-Host "This may take a few minutes and might ask to reboot." -ForegroundColor White
Write-Host ""

wsl --install -d Ubuntu

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "=== Done! ===" -ForegroundColor Green
    Write-Host "If prompted, restart your PC to finish setup." -ForegroundColor Yellow
    Write-Host "After reboot, open PowerShell and type: wsl" -ForegroundColor White
    Write-Host "It will ask you to create a Linux username and password." -ForegroundColor White
} else {
    Write-Host ""
    Write-Host "WSL install hit an issue." -ForegroundColor Red
    Write-Host "Try these manual steps:" -ForegroundColor Yellow
    Write-Host "  1. Open Microsoft Store" -ForegroundColor White
    Write-Host "  2. Search for 'Ubuntu'" -ForegroundColor White
    Write-Host "  3. Click Install" -ForegroundColor White
    Write-Host ""
    Write-Host "Or try running this in PowerShell:" -ForegroundColor Yellow
    Write-Host "  wsl --install --web-download" -ForegroundColor White
}

Write-Host ""
Read-Host "Press Enter to exit"
