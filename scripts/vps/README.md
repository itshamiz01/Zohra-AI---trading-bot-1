# Zohra on a Windows VPS — setup guide

Goal: your MT5 account and the Zohra bot run 24/7 on a rented Windows server.
Your laptop is out of the loop. Total new cost: the VPS only (about $16/month on the recommended option). No MetaApi, no per-account fees.

## Step 1 — Rent the VPS (you do this; it needs your payment)

Buy this shape or bigger:

- Windows Server 2022, 2 vCPU or more, 4 GB RAM or more, 60 GB+ SSD
- Location: Singapore or Germany (London also fine). Your demo strategy does not need ultra-low latency.

Recommended options (prices checked from public pricing guides, October 2026 — confirm the total at checkout, Windows licence included):

| Provider | Shape | Price/month | Why |
|---|---|---|---|
| Contabo Cloud VPS 4 | 4 vCPU, 8 GB RAM, 100 GB SSD | about $16.20 | Cheapest all-in, more power than needed |
| ForexVPS.net Core | 2 vCPU, 4 GB RAM, 100 GB | about $28.80 (yearly billing) | Trading-specialist, MT5-friendly, many cities |
| Kamatera Type A | 2 vCPU, 4 GB RAM, 40 GB NVMe | about $38 | Hourly billing, cancel anytime, many locations |
| AWS Lightsail | 2 vCPU, 4 GB RAM, 80 GB SSD | about $44 | Biggest name, very simple console |

After payment the provider emails you: server IP, username (usually Administrator) and a password. Keep that email. Do not paste the password into any chat — you type it into Remote Desktop yourself.

## Step 2 — Connect to the VPS (you)

- On your PC: open "Remote Desktop Connection" (mstsc), enter the server IP, log in as Administrator with the emailed password. Change the password when Windows offers.
- On your phone: the Microsoft "Windows App" / RD Client does the same job.

## Step 3 — Run the installer (you paste one block; I wrote the script)

Open PowerShell **as Administrator** inside the VPS and run:

```powershell
git --version
```

If Git is not there yet, that is fine — the installer adds it. Download and run the installer from your own repo:

```powershell
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/itshamiz01/Zohra-AI---trading-bot-1/main/scripts/vps/Install-ZohraVPS.ps1" -OutFile "$env:TEMP\Install-ZohraVPS.ps1"
powershell -ExecutionPolicy Bypass -File "$env:TEMP\Install-ZohraVPS.ps1"
```

The installer: installs Git, Python 3.12 and MetaTrader 5; clones the bot to `C:\Zohra`; installs dependencies including the official MetaTrader5 Python package; creates `C:\Zohra\.env`; registers two auto-start tasks (ZohraMT5 and ZohraBot) that relaunch after any reboot.

## Step 4 — Sign in to MT5 (you; password never leaves the VPS)

- Open MetaTrader 5 on the VPS.
- If your old demo login does not work (the copy in the repo turned out to be dead), create a fresh one inside MT5: **File → Open an Account → MetaQuotes Ltd → Open a demo account**. Note the new login, password and server it shows you.
- Sign in and leave MT5 running.
- Open `C:\Zohra\.env` in Notepad and set `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER` to that same demo account. Save.

## Step 5 — Start it and check (you, then me)

- Reboot the VPS once. Both tasks fire at logon.
- On the VPS, open a browser to `http://127.0.0.1:8000` — the Zohra dashboard should load with your demo account visible.
- When you disconnect Remote Desktop, choose **disconnect**, not log off — MT5 must stay in a live session.
- Tell Muse "VPS is up" and the server's public IP (the IP is fine to share; the password is not).

## Step 6 — Secure remote dashboard + Vercel frontend (Muse guides, you approve)

- Install Tailscale on the VPS and on your phone/PC, same account. The dashboard then opens privately at the VPS's Tailscale address — visible only to your devices.
- Muse then repoints the Vercel frontend's API rewrite to the VPS over a secured route and verifies the full chain: dashboard → VPS bot → MT5 demo → paper trades executing.

## Rules that keep this safe

- Demo account only, until you deliberately decide otherwise after months of paper results.
- Trading password is typed only inside the VPS (MT5 login and `C:\Zohra\.env`). Never in chat, never in email.
- The bot API binds to localhost on the VPS. Nothing trading-related is exposed to the open internet.
