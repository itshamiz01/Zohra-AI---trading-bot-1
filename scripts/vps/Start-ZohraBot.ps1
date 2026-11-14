# Zohra bot launcher — called by the "ZohraBot" scheduled task at logon.
# Starts the trading engine in demo mode, then the API/dashboard bound to
# this machine's Tailscale address when Tailscale is up (reachable only
# from your own devices), otherwise localhost only. Never binds publicly.
$Root = "C:\Zohra"
Set-Location $Root
$Py = "$Root\.venv\Scripts\python.exe"
$LogDir = "$Root\logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

# Engine (paper trading on the demo account configured in .env)
Start-Process -FilePath $Py -ArgumentList "main.py demo" -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput "$LogDir\engine.out.log" -RedirectStandardError "$LogDir\engine.err.log"

# Dashboard bind address: Tailscale IP if available, else localhost
$BindHost = "127.0.0.1"
$TsCmd = Get-Command tailscale -ErrorAction SilentlyContinue
if ($TsCmd) {
    try {
        $TsIp = (& tailscale ip -4 2>$null | Select-Object -First 1)
        if ($TsIp -match '^\d+\.\d+\.\d+\.\d+$') { $BindHost = $TsIp.Trim() }
    } catch { }
}
Start-Process -FilePath $Py -ArgumentList "-m uvicorn zohra.api.app:app --host $BindHost --port 8000" -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput "$LogDir\api.out.log" -RedirectStandardError "$LogDir\api.err.log"
