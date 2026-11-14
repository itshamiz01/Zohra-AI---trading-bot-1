# run_zohra_daemon.ps1
# Zohra 24/7 Auto-Recovery Daemon Runner

$ErrorActionPreference = "Continue"
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   ZOHRA QUANTITATIVE ENGINE 24/7 DAEMON ACTIVE           " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop the daemon and exit trading." -ForegroundColor Yellow

while ($true) {
    Write-Host "[$(Get-Date)] Starting Zohra central brain..." -ForegroundColor Green
    
    # Run the Zohra orchestrator in the current console window and wait for it to exit
    python zohra.py --mode demo
    
    Write-Host "[$(Get-Date)] Zohra process exited or crashed! Restarting in 10 seconds..." -ForegroundColor Red
    Start-Sleep -Seconds 10
}
