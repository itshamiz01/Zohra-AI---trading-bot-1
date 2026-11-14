# Zohra bot launcher — called by the "ZohraBot" scheduled task at logon.
# Starts the trading engine in demo mode and the API/dashboard server
# bound to localhost only (reach it privately via Tailscale, never open).
$Root = "C:\Zohra"
Set-Location $Root
$Py = "$Root\.venv\Scripts\python.exe"
$LogDir = "$Root\logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

# Engine (paper trading on the demo account configured in .env)
Start-Process -FilePath $Py -ArgumentList "main.py demo" -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput "$LogDir\engine.out.log" -RedirectStandardError "$LogDir\engine.err.log"

# API + dashboard on localhost only
Start-Process -FilePath $Py -ArgumentList "-m uvicorn zohra.api.app:app --host 127.0.0.1 --port 8000" -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput "$LogDir\api.out.log" -RedirectStandardError "$LogDir\api.err.log"
