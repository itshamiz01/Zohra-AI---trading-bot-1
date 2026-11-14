# Zohra on your own Windows machine at home — checklist

Cost: 0. The machine stays plugged in at home; you never carry it or open it again.
The dashboard reaches your phone privately through Tailscale (free).

## 1) Prepare the machine (2 minutes)

- Plug in the charger and leave it plugged in.
- Connect to your home Wi-Fi.
- Log in to Windows as usual.

## 2) Run the installer (one paste)

Open **PowerShell as Administrator** (Start menu → type PowerShell → right-click → Run as administrator), then paste these two lines:

```powershell
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/itshamiz01/Zohra-AI---trading-bot-1/main/scripts/vps/Install-ZohraVPS.ps1" -OutFile "$env:TEMP\Install-ZohraVPS.ps1"
powershell -ExecutionPolicy Bypass -File "$env:TEMP\Install-ZohraVPS.ps1"
```

It installs Git, Python, MetaTrader 5 (keeps yours if already installed), Tailscale and the bot at `C:\Zohra`, stops the machine sleeping, and registers auto-start for MT5 and the bot.
If anything prints in red, copy that text and send it to Muse — do not keep retrying.

## 3) Sign in to MT5 (password stays on this machine)

- Open MetaTrader 5.
- Your old demo login is dead, so create a fresh one: **File → Open an Account → MetaQuotes Ltd → Open a demo account**. Write down the login, password and server it shows.
- Sign in and leave MT5 open.
- Open `C:\Zohra\.env` in Notepad and set `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER` to those exact values. Save.

## 4) Two one-time settings

- Control Panel → Power Options → "Choose what closing the lid does" → for **Plugged in**, set **Do nothing**. Save.
- Open **Tailscale** from the Start menu and sign in. Install Tailscale on your phone too, same account.

## 5) Reboot and check

- Restart the machine and log in. MT5 and the bot start on their own.
- On the machine, open `http://127.0.0.1:8000` — the Zohra dashboard should show your demo account.
- On your phone (Tailscale on), the same dashboard opens at the machine's Tailscale address — Muse will confirm the exact address with you.

## 6) Tell Muse

Send: **"Home server is up"** — plus the Tailscale address if you see it (an address like 100.x.x.x is safe to share; passwords never are).
Muse then verifies the bot end to end and finishes the secure wiring.

## Daily life after setup

- Keep it plugged in. Closing the lid is fine. After any power cut, just switch it on and log in once — everything restarts itself.
- Demo account only. Nothing real-money is involved.
