# Zohra VPS installer — run ONCE in PowerShell as Administrator on the Windows VPS.
# Installs Git, Python, MetaTrader 5 and the Zohra bot, then registers
# auto-start tasks so MT5 and the bot come back after any reboot.
# It never asks for your trading password. You sign in to MT5 and fill
# C:\Zohra\.env yourself, on the VPS, after this script finishes.
$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/itshamiz01/Zohra-AI---trading-bot-1.git"
$Root = "C:\Zohra"

Write-Host "== 1/6 Installing Git and Python ==" -ForegroundColor Cyan
winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements
winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

Write-Host "== 2/6 Installing MetaTrader 5 ==" -ForegroundColor Cyan
$Mt5Setup = "$env:TEMP\mt5setup.exe"
Invoke-WebRequest -Uri "https://download.mql5.com/cdn/web/metaquotes.ltd/mt5/mt5setup.exe" -OutFile $Mt5Setup
Start-Process -FilePath $Mt5Setup -ArgumentList "/auto" -Wait
Write-Host "MT5 installed (default location: C:\Program Files\MetaTrader 5)."

Write-Host "== 3/6 Downloading the Zohra bot ==" -ForegroundColor Cyan
if (Test-Path $Root) { Write-Host "C:\Zohra already exists, pulling latest..."; git -C $Root pull } else { git clone $RepoUrl $Root }
Set-Location $Root

Write-Host "== 4/6 Installing Python dependencies (includes the MetaTrader5 package) ==" -ForegroundColor Cyan
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt

Write-Host "== 5/6 Preparing your private .env ==" -ForegroundColor Cyan
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env"; Write-Host "Created C:\Zohra\.env from the example. You MUST edit it with your working demo login/password/server before starting the bot." }
& .\.venv\Scripts\python.exe -c "import MetaTrader5 as mt5; print('MetaTrader5 package OK, version:', mt5.__version__)"

Write-Host "== 6/6 Registering auto-start tasks ==" -ForegroundColor Cyan
$BotScript = "$Root\scripts\vps\Start-ZohraBot.ps1"
$ActionBot = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$BotScript`""
$TriggerLogon = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName "ZohraBot" -Action $ActionBot -Trigger $TriggerLogon -Settings $Settings -RunLevel Highest -Force | Out-Null
$Mt5Exe = "C:\Program Files\MetaTrader 5\terminal64.exe"
if (Test-Path $Mt5Exe) {
    $ActionMt5 = New-ScheduledTaskAction -Execute $Mt5Exe
    Register-ScheduledTask -TaskName "ZohraMT5" -Action $ActionMt5 -Trigger $TriggerLogon -Settings $Settings -RunLevel Highest -Force | Out-Null
}
Write-Host ""
Write-Host "DONE. Next steps, all on this VPS:" -ForegroundColor Green
Write-Host " 1) Open MetaTrader 5 and sign in to your DEMO account (or create a fresh demo in MT5: File > Open an Account > MetaQuotes Ltd)."
Write-Host " 2) Edit C:\Zohra\.env and set MT5_LOGIN, MT5_PASSWORD and MT5_SERVER to that same demo account. Save."
Write-Host " 3) Reboot the VPS once (or log off/on) so both auto-start tasks fire, then check the dashboard."
Write-Host "    Keep your RDP session logged in (disconnect, do not log off) so MT5 keeps running."
