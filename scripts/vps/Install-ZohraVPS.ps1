# Zohra home/VPS installer — run ONCE in PowerShell as Administrator on the Windows machine.
# Works on a rented Windows VPS and on your own Windows machine at home.
# Installs Git, Python, MetaTrader 5, Tailscale and the Zohra bot, stops the
# machine sleeping, then registers auto-start tasks so MT5 and the bot come
# back after any reboot (you only need to log in to Windows once).
# It never asks for your trading password. You sign in to MT5 and fill
# C:\Zohra\.env yourself, on this machine, after this script finishes.
$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/itshamiz01/Zohra-AI---trading-bot-1.git"
$Root = "C:\Zohra"

Write-Host "== 1/7 Never sleep while plugged in ==" -ForegroundColor Cyan
powercfg /change standby-timeout-ac 0
powercfg /change monitor-timeout-ac 0
powercfg /hibernate off
Write-Host "Sleep and hibernation disabled on AC power. Also set 'When I close the lid' to 'Do nothing' in Power Options later."

Write-Host "== 2/7 Installing Git, Python and Tailscale ==" -ForegroundColor Cyan
winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements
winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
winget install --id Tailscale.Tailscale -e --accept-source-agreements --accept-package-agreements
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

Write-Host "== 3/7 MetaTrader 5 (keeps any existing install) ==" -ForegroundColor Cyan
$Mt5Candidates = @("C:\Program Files\MetaTrader 5\terminal64.exe", "C:\Program Files\MetaTrader 5 A\terminal64.exe")
$Mt5Exe = $Mt5Candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($Mt5Exe) {
    Write-Host "Existing MT5 found at $Mt5Exe — keeping it."
} else {
    $Mt5Setup = "$env:TEMP\mt5setup.exe"
    Invoke-WebRequest -Uri "https://download.mql5.com/cdn/web/metaquotes.ltd/mt5/mt5setup.exe" -OutFile $Mt5Setup
    Start-Process -FilePath $Mt5Setup -ArgumentList "/auto" -Wait
    $Mt5Exe = $Mt5Candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    Write-Host "MT5 installed at $Mt5Exe"
}

Write-Host "== 4/7 Downloading the Zohra bot ==" -ForegroundColor Cyan
if (Test-Path $Root) { Write-Host "C:\Zohra already exists, pulling latest..."; git -C $Root pull } else { git clone $RepoUrl $Root }
Set-Location $Root

Write-Host "== 5/7 Installing Python dependencies (includes the MetaTrader5 package) ==" -ForegroundColor Cyan
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt

Write-Host "== 6/7 Preparing your private .env ==" -ForegroundColor Cyan
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env"; Write-Host "Created C:\Zohra\.env from the example. You MUST edit it with your working demo login/password/server before starting the bot." }
& .\.venv\Scripts\python.exe -c "import MetaTrader5 as mt5; print('MetaTrader5 package OK, version:', mt5.__version__)"

Write-Host "== 7/7 Registering auto-start tasks ==" -ForegroundColor Cyan
$BotScript = "$Root\scripts\vps\Start-ZohraBot.ps1"
$ActionBot = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$BotScript`""
$TriggerLogon = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName "ZohraBot" -Action $ActionBot -Trigger $TriggerLogon -Settings $Settings -RunLevel Highest -Force | Out-Null
if ($Mt5Exe) {
    $ActionMt5 = New-ScheduledTaskAction -Execute $Mt5Exe
    Register-ScheduledTask -TaskName "ZohraMT5" -Action $ActionMt5 -Trigger $TriggerLogon -Settings $Settings -RunLevel Highest -Force | Out-Null
}
Write-Host ""
Write-Host "DONE. Next steps, all on this machine:" -ForegroundColor Green
Write-Host " 1) Open MetaTrader 5 and sign in to your DEMO account (or create a fresh demo in MT5: File > Open an Account > MetaQuotes Ltd)."
Write-Host " 2) Edit C:\Zohra\.env and set MT5_LOGIN, MT5_PASSWORD and MT5_SERVER to that same demo account. Save."
Write-Host " 3) In Control Panel > Power Options, set 'When I close the lid' (plugged in) to 'Do nothing'."
Write-Host " 4) Open Tailscale from the Start menu and sign in (same account you will use on your phone)."
Write-Host " 5) Reboot once and log in. MT5 and the bot start by themselves. Check the dashboard at http://127.0.0.1:8000"
Write-Host "    After that, just keep the machine plugged in. Closing the lid is fine."
