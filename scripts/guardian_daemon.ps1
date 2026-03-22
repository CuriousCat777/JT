# Guardian One — Windows Daemon (Task Scheduler Bootstrap)
# Runs financial sync + daily review cycle
# Schedule via: schtasks or Task Scheduler GUI
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File "C:\Users\jerem\JT\scripts\guardian_daemon.ps1"

$ErrorActionPreference = "Continue"
$JT_DIR = "C:\Users\jerem\JT"
$PYTHON = "C:\Python314\python.exe"
$LOG_DIR = "$JT_DIR\logs"
$TIMESTAMP = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$LOG_FILE = "$LOG_DIR\daemon_$TIMESTAMP.log"

# Ensure log directory exists
if (-not (Test-Path $LOG_DIR)) { New-Item -ItemType Directory -Path $LOG_DIR -Force | Out-Null }

function Write-Log {
    param([string]$Message)
    $entry = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | $Message"
    Add-Content -Path $LOG_FILE -Value $entry
    Write-Host $entry
}

Write-Log "Guardian One daemon starting..."
Set-Location $JT_DIR

# 1. Financial sync (single cycle)
Write-Log "Running CFO sync..."
try {
    & $PYTHON main.py --sync-once 2>&1 | ForEach-Object { Write-Log "  [sync] $_" }
    Write-Log "CFO sync complete."
} catch {
    Write-Log "CFO sync error: $_"
}

# 2. Daily review + notifications
Write-Log "Running daily review..."
try {
    & $PYTHON main.py --summary 2>&1 | ForEach-Object { Write-Log "  [summary] $_" }
    Write-Log "Daily review complete."
} catch {
    Write-Log "Daily review error: $_"
}

# 3. Notion dashboard push
Write-Log "Pushing Notion dashboards..."
try {
    & $PYTHON main.py --notion-sync 2>&1 | ForEach-Object { Write-Log "  [notion] $_" }
    Write-Log "Notion sync complete."
} catch {
    Write-Log "Notion sync error: $_"
}

Write-Log "Guardian One daemon cycle finished."
