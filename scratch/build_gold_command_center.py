import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

# Ensure static directory has the portrait
static_img = os.path.join("zohra", "api", "static", "zohra_portrait.png")
if not os.path.exists(static_img):
    print("Warning: static portrait missing, will verify extraction.")

dashboard_html = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ZOHRA AI OS // COMMAND CENTER</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800;900&family=Space+Grotesk:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/apexcharts"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>

    <style>
        :root {
            --bg-void: #020204;
            --bg-panel: rgba(10, 11, 16, 0.88);
            --bg-panel-hover: rgba(16, 18, 26, 0.95);
            --gold-primary: #d4af37;
            --gold-bright: #ffd700;
            --gold-light: #f5df88;
            --gold-dim: #8e7827;
            --gold-border: rgba(212, 175, 55, 0.22);
            --gold-border-bright: rgba(212, 175, 55, 0.45);
            --gold-glow: rgba(212, 175, 55, 0.15);
            --text-white: #ffffff;
            --text-gold: #e5c158;
            --text-muted: #8e8671;
            --text-dim: #5c5545;
            --green-emerald: #00ffcc;
            --green-glow: rgba(0, 255, 204, 0.25);
            --red-ruby: #ff007f;
            --amber-warn: #ffaa00;
            --sidebar-width: 210px;
            --right-col-width: 290px;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            scrollbar-width: thin;
            scrollbar-color: var(--gold-border) transparent;
        }

        body {
            background-color: var(--bg-void);
            font-family: 'Space Grotesk', -apple-system, BlinkMacSystemFont, sans-serif;
            color: var(--text-white);
            height: 100vh;
            width: 100vw;
            overflow: hidden;
            background-image: 
                radial-gradient(circle at 50% 30%, rgba(212, 175, 55, 0.04) 0%, transparent 60%),
                radial-gradient(circle at 80% 80%, rgba(212, 175, 55, 0.02) 0%, transparent 50%);
        }

        /* ─── APP SHELL ─── */
        .app-shell {
            display: grid;
            grid-template-rows: 54px 1fr;
            height: 100vh;
            width: 100vw;
            overflow: hidden;
        }

        /* ─── TOPBAR ─── */
        .os-topbar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0 24px;
            background: rgba(4, 5, 8, 0.95);
            border-bottom: 1px solid var(--gold-border);
            z-index: 100;
            position: relative;
        }
        .brand-left {
            display: flex;
            flex-direction: column;
            gap: 1px;
        }
        .brand-title {
            font-family: 'Outfit', sans-serif;
            font-size: 19px;
            font-weight: 900;
            letter-spacing: 2px;
            color: var(--gold-bright);
            text-shadow: 0 0 12px var(--gold-glow);
            line-height: 1.1;
        }
        .brand-sub {
            font-size: 9px;
            letter-spacing: 3px;
            color: var(--text-muted);
            text-transform: uppercase;
        }

        /* Angular Sci-Fi Banner */
        .center-hud-banner {
            background: rgba(14, 15, 22, 0.9);
            border: 1px solid var(--gold-border);
            padding: 5px 28px;
            clip-path: polygon(14px 0, calc(100% - 14px) 0, 100% 100%, 0 100%);
            font-family: 'Outfit', sans-serif;
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 2.5px;
            color: var(--text-gold);
            text-transform: uppercase;
            box-shadow: 0 0 15px rgba(212,175,55,0.08);
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .topbar-right {
            display: flex;
            align-items: center;
            gap: 16px;
        }
        .account-selector-box {
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(18, 20, 28, 0.9);
            border: 1px solid var(--gold-border);
            border-radius: 6px;
            padding: 4px 10px;
        }
        .account-selector-box select {
            background: transparent;
            border: none;
            color: var(--text-gold);
            font-family: 'Space Grotesk', monospace;
            font-size: 12px;
            font-weight: 600;
            outline: none;
            cursor: pointer;
        }
        .account-selector-box select option {
            background: #0d0f17;
            color: #fff;
        }
        .demo-pill {
            font-size: 9px;
            font-weight: 800;
            background: rgba(212, 175, 55, 0.15);
            color: var(--gold-bright);
            border: 1px solid var(--gold-border);
            padding: 2px 6px;
            border-radius: 4px;
            letter-spacing: 1px;
        }
        .topbar-icons {
            display: flex;
            align-items: center;
            gap: 12px;
            color: var(--text-muted);
            font-size: 14px;
            cursor: pointer;
        }
        .topbar-icons span:hover {
            color: var(--gold-bright);
        }
        .time-box {
            text-align: right;
            border-left: 1px solid var(--gold-border);
            padding-left: 14px;
        }
        .time-label {
            font-size: 8px;
            letter-spacing: 1.5px;
            color: var(--text-muted);
            text-transform: uppercase;
        }
        .time-val {
            font-family: 'Space Grotesk', monospace;
            font-size: 12px;
            font-weight: 700;
            color: var(--gold-light);
        }

        /* ─── MAIN LAYOUT ─── */
        .os-main {
            display: grid;
            grid-template-columns: var(--sidebar-width) 1fr var(--right-col-width);
            height: calc(100vh - 54px);
            overflow: hidden;
            position: relative;
        }

        /* ─── LEFT SIDEBAR ─── */
        .os-sidebar {
            background: rgba(5, 6, 10, 0.95);
            border-right: 1px solid var(--gold-border);
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            padding: 14px 10px;
            overflow-y: auto;
            z-index: 50;
        }
        .radar-reticle {
            width: 70px;
            height: 70px;
            margin: 0 auto 14px;
            border-radius: 50%;
            border: 1px dashed var(--gold-border);
            position: relative;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 0 15px rgba(212, 175, 55, 0.08);
            animation: rotateReticle 24s linear infinite;
        }
        @keyframes rotateReticle {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }
        .reticle-z {
            font-family: 'Outfit', sans-serif;
            font-size: 26px;
            font-weight: 900;
            color: var(--gold-bright);
            text-shadow: 0 0 12px var(--gold-glow);
            transform: rotate(0deg); /* un-rotate */
            animation: unRotateReticle 24s linear infinite;
        }
        @keyframes unRotateReticle {
            from { transform: rotate(0deg); }
            to { transform: rotate(-360deg); }
        }

        .nav-menu {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        .nav-item {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 1px;
            text-transform: uppercase;
            color: var(--text-muted);
            cursor: pointer;
            transition: all 0.2s ease;
            border: 1px solid transparent;
            user-select: none;
        }
        .nav-item:hover {
            color: var(--text-white);
            background: rgba(212, 175, 55, 0.06);
            border-color: rgba(212, 175, 55, 0.15);
        }
        .nav-item.active {
            color: var(--gold-bright);
            background: rgba(212, 175, 55, 0.08);
            border: 1px solid var(--gold-border-bright);
            box-shadow: 0 0 12px rgba(212, 175, 55, 0.12);
        }
        .nav-icon {
            font-size: 13px;
            width: 16px;
            text-align: center;
        }

        /* Sidebar Bottom Status Card */
        .sidebar-status-card {
            background: rgba(14, 16, 24, 0.85);
            border: 1px solid var(--gold-border);
            border-radius: 8px;
            padding: 10px 12px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-top: 10px;
        }
        .status-left {
            display: flex;
            flex-direction: column;
            gap: 2px;
        }
        .status-badge-title {
            font-size: 8px;
            color: var(--text-muted);
            letter-spacing: 1px;
            text-transform: uppercase;
        }
        .status-state-live {
            font-size: 12px;
            font-weight: 800;
            color: var(--green-emerald);
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .health-ring-box {
            position: relative;
            width: 44px;
            height: 44px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .health-ring-svg {
            transform: rotate(-90deg);
            width: 44px;
            height: 44px;
        }
        .health-ring-bg {
            stroke: rgba(255, 255, 255, 0.08);
            stroke-width: 3;
            fill: none;
        }
        .health-ring-val {
            stroke: var(--green-emerald);
            stroke-width: 3;
            stroke-dasharray: 100;
            stroke-dashoffset: 2;
            stroke-linecap: round;
            fill: none;
            transition: stroke-dashoffset 0.8s ease;
        }
        .health-text-inner {
            position: absolute;
            font-family: 'Outfit', sans-serif;
            font-size: 11px;
            font-weight: 800;
            color: #fff;
        }

        /* ─── WORKSPACE VIEWS ─── */
        .workspace-view {
            display: none;
            width: 100%;
            height: 100%;
        }
        .workspace-view.active {
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            width: 100%;
            height: 100%;
        }

        /* ─── CENTER STAGE ─── */
        .os-center {
            position: relative;
            height: 100%;
            overflow: hidden;
            padding: 22px 24px 20px;
            background: radial-gradient(circle at 50% 45%, rgba(212, 175, 55, 0.05) 0%, transparent 68%);
        }

        /* Subtle Constellation Canvas Background */
        #celestial-particle-canvas {
            position: absolute;
            inset: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: 1;
        }

        /* Greeting */
        .greeting-hud {
            position: absolute;
            top: 22px;
            left: 24px;
            z-index: 10;
            max-width: 350px;
        }
        .greeting-sub {
            font-size: 11px;
            letter-spacing: 2px;
            color: var(--gold-light);
            text-transform: uppercase;
            font-weight: 600;
        }
        .greeting-name {
            font-family: 'Outfit', sans-serif;
            font-size: 32px;
            font-weight: 900;
            color: var(--text-white);
            letter-spacing: 1.5px;
            margin: 2px 0 4px;
            text-shadow: 0 0 20px rgba(255, 255, 255, 0.2);
        }
        .greeting-prompt {
            font-size: 13px;
            color: var(--text-muted);
        }

        /* 3D Molecular Hologram Stage - Large & Prominent */
        .central-hologram-stage {
            position: absolute;
            top: 44%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 820px;
            height: 620px;
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 5;
            pointer-events: auto;
        }
        #zohra-hologram-canvas {
            width: 100%;
            height: 100%;
            display: block;
        }
        .hologram-status-pill {
            position: absolute;
            bottom: 6px;
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(10, 12, 18, 0.88);
            border: 1px solid var(--gold-border);
            border-radius: 20px;
            padding: 4px 14px;
            font-size: 9px;
            letter-spacing: 2px;
            color: var(--gold-light);
            text-transform: uppercase;
            box-shadow: 0 0 15px rgba(212, 175, 55, 0.12);
            pointer-events: none;
        }
        .holo-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: var(--gold-bright);
            box-shadow: 0 0 8px var(--gold-bright);
            animation: holoDotPulse 1.8s infinite ease-in-out;
        }
        @keyframes holoDotPulse {
            0%, 100% { transform: scale(0.9); opacity: 0.6; }
            50% { transform: scale(1.3); opacity: 1.0; }
        }

        /* Center Bottom Summary Cards */
        .bottom-cards-grid {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 12px;
            z-index: 10;
            position: absolute;
            bottom: 20px;
            left: 24px;
            right: 24px;
        }
        .summary-card {
            background: var(--bg-panel);
            border: 1px solid var(--gold-border);
            border-radius: 8px;
            padding: 12px 14px;
            transition: all 0.25s ease;
            position: relative;
            overflow: hidden;
            cursor: pointer;
        }
        .summary-card:hover {
            border-color: var(--gold-border-bright);
            background: var(--bg-panel-hover);
            transform: translateY(-2px);
            box-shadow: 0 4px 20px rgba(0,0,0,0.6), 0 0 15px rgba(212, 175, 55, 0.08);
        }
        .card-hdr {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 10px;
            font-weight: 800;
            letter-spacing: 1px;
            color: var(--gold-light);
            text-transform: uppercase;
            margin-bottom: 6px;
        }
        .card-metric-label {
            font-size: 9px;
            color: var(--text-muted);
            letter-spacing: 1px;
            text-transform: uppercase;
        }
        .card-metric-val {
            font-family: 'Outfit', sans-serif;
            font-size: 20px;
            font-weight: 900;
            color: #fff;
            margin: 2px 0;
        }
        .card-metric-sub {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 11px;
            font-weight: 700;
        }
        .sub-win { color: var(--green-emerald); }
        .sub-loss { color: var(--red-ruby); }
        
        .sparkline-svg {
            width: 60px;
            height: 20px;
            overflow: visible;
        }

        /* ─── RIGHT COLUMN ─── */
        .os-right {
            background: rgba(5, 6, 10, 0.95);
            border-left: 1px solid var(--gold-border);
            display: flex;
            flex-direction: column;
            gap: 12px;
            padding: 14px;
            overflow-y: auto;
            z-index: 50;
        }
        .panel-box {
            background: var(--bg-panel);
            border: 1px solid var(--gold-border);
            border-radius: 8px;
            padding: 12px 14px;
            position: relative;
        }
        .panel-box-hdr {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 11px;
            font-weight: 800;
            letter-spacing: 1.5px;
            color: var(--gold-light);
            text-transform: uppercase;
            margin-bottom: 10px;
        }

        /* AI Agent Network Graph & Counters */
        .agent-network-row {
            display: grid;
            grid-template-columns: 100px 1fr;
            gap: 10px;
            align-items: center;
        }
        .network-svg-box {
            width: 96px;
            height: 96px;
            position: relative;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .network-svg {
            width: 100%;
            height: 100%;
        }
        .network-stats-list {
            display: flex;
            flex-direction: column;
            gap: 4px;
            font-size: 11px;
            font-family: 'Space Grotesk', monospace;
        }
        .net-stat-item {
            display: flex;
            justify-content: space-between;
            color: var(--text-muted);
        }
        .net-stat-item strong {
            color: var(--gold-light);
        }
        .view-agents-btn {
            margin-top: 10px;
            width: 100%;
            padding: 6px;
            background: rgba(212, 175, 55, 0.08);
            border: 1px solid var(--gold-border);
            border-radius: 6px;
            color: var(--text-gold);
            font-size: 10px;
            font-weight: 800;
            letter-spacing: 1.5px;
            text-transform: uppercase;
            cursor: pointer;
            transition: all 0.2s;
        }
        .view-agents-btn:hover {
            background: var(--gold-primary);
            color: #000;
            box-shadow: 0 0 15px var(--gold-glow);
        }

        /* Performance Circular Rings */
        .rings-row {
            display: flex;
            justify-content: space-around;
            align-items: center;
            margin-top: 4px;
        }
        .ring-item {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 4px;
        }
        .ring-container {
            width: 58px;
            height: 58px;
            position: relative;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .ring-svg {
            width: 58px;
            height: 58px;
            transform: rotate(-90deg);
        }
        .ring-bg-circle {
            stroke: rgba(255, 255, 255, 0.07);
            stroke-width: 4;
            fill: none;
        }
        .ring-val-circle {
            stroke: var(--gold-bright);
            stroke-width: 4;
            stroke-dasharray: 100;
            stroke-linecap: round;
            fill: none;
            transition: stroke-dashoffset 0.6s ease;
        }
        .ring-pct-txt {
            position: absolute;
            font-family: 'Outfit', sans-serif;
            font-size: 12px;
            font-weight: 800;
            color: #fff;
        }
        .ring-lbl {
            font-size: 9px;
            font-weight: 700;
            color: var(--text-muted);
            letter-spacing: 1px;
        }

        /* Active Operations */
        .ops-list {
            display: flex;
            flex-direction: column;
            gap: 7px;
            font-size: 11px;
        }
        .op-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .op-name {
            display: flex;
            align-items: center;
            gap: 6px;
            color: var(--text-white);
        }
        .op-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: var(--green-emerald);
            box-shadow: 0 0 8px var(--green-emerald);
        }
        .op-dot.amber {
            background: var(--amber-warn);
            box-shadow: 0 0 8px var(--amber-warn);
        }
        .op-state {
            font-size: 10px;
            font-weight: 700;
            color: var(--green-emerald);
        }
        .op-state.training { color: var(--amber-warn); }

        /* ZOHRA Voice Waveform */
        .waveform-box {
            height: 48px;
            width: 100%;
            position: relative;
            display: flex;
            align-items: center;
            justify-content: center;
            background: rgba(0,0,0,0.3);
            border-radius: 6px;
            overflow: hidden;
            border: 1px solid rgba(255,255,255,0.04);
        }
        #voice-canvas {
            width: 100%;
            height: 100%;
        }
        .voice-mic-status {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 11px;
            color: var(--text-muted);
            margin-top: 6px;
            cursor: pointer;
        }
        .voice-mic-status:hover {
            color: var(--gold-bright);
        }

        /* ─── WORKSPACE VIEWS (Trading, Risk, Memory, Learning, etc.) ─── */
        .workspace-view {
            display: none;
            padding: 20px 28px;
            height: 100%;
            overflow-y: auto;
        }
        .workspace-view.active {
            display: block;
        }

        /* Trading Division Tables */
        .table-panel {
            background: var(--bg-panel);
            border: 1px solid var(--gold-border);
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 16px;
        }
        .os-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
            margin-top: 10px;
        }
        .os-table th {
            text-align: left;
            padding: 8px 10px;
            color: var(--gold-light);
            border-bottom: 1px solid var(--gold-border);
            font-size: 10px;
            letter-spacing: 1px;
            text-transform: uppercase;
        }
        .os-table td {
            padding: 8px 10px;
            border-bottom: 1px solid rgba(255,255,255,0.04);
        }
        .badge-buy {
            background: rgba(0,255,204,0.15);
            color: var(--green-emerald);
            padding: 2px 6px;
            border-radius: 4px;
            font-weight: 700;
        }
        .badge-sell {
            background: rgba(255,0,127,0.15);
            color: var(--red-ruby);
            padding: 2px 6px;
            border-radius: 4px;
            font-weight: 700;
        }

        /* Responsive */
        @media (max-width: 1280px) {
            .app-shell {
                overflow: auto;
            }
            .os-main {
                grid-template-columns: 180px 1fr;
            }
            .os-right {
                display: none;
            }
            .bottom-cards-grid {
                grid-template-columns: repeat(3, 1fr);
            }
        }
    </style>
</head>
<body>

    <div class="app-shell">
        
        <!-- ═══ TOPBAR ═══ -->
        <header class="os-topbar">
            <div class="brand-left">
                <div class="brand-title">ZOHRA</div>
                <div class="brand-sub">AI OS ★ v1.7.3</div>
            </div>

            <div class="center-hud-banner">
                <span>ZOHRA AI OS // COMMAND CENTER</span>
            </div>

            <div class="topbar-right">
                <!-- Persistent Multi-Account Selector -->
                <div class="account-selector-box" title="Switch MT5 Account Context">
                    <span style="color:var(--gold-bright);font-size:12px;">⚡</span>
                    <select id="os-account-selector" onchange="onAccountSelectorChange(this.value)">
                        <option value="all">ALL FLEET (3 Accounts)</option>
                        <option value="account_01">Account 1 (Primary #10012413413)</option>
                        <option value="account_02">Account 2 (Secondary #5055123669)</option>
                        <option value="account_03">Account 3 (Tertiary #10012413431)</option>
                    </select>
                    <span class="demo-pill">DEMO</span>
                </div>

                <div class="topbar-icons">
                    <span title="Search">🔍</span>
                    <span title="Notifications" style="position:relative;">🔔<span style="position:absolute;top:-4px;right:-4px;width:6px;height:6px;background:red;border-radius:50%;"></span></span>
                    <span title="Brightness">☀️</span>
                    <span title="Settings" onclick="switchView('settings')">⚙️</span>
                </div>

                <div class="time-box">
                    <div class="time-label">SYSTEM TIME</div>
                    <div class="time-val" id="top-system-time">11:47:32 PM</div>
                </div>
            </div>
        </header>

        <!-- ═══ MAIN THREE-PANE BODY ═══ -->
        <div class="os-main">

            <!-- ─── LEFT SIDEBAR ─── -->
            <nav class="os-sidebar">
                <div>
                    <!-- Radar Monogram Reticle -->
                    <div class="radar-reticle" title="ZOHRA Neural Matrix Active">
                        <div class="reticle-z">Z</div>
                    </div>

                    <!-- Menu List -->
                    <div class="nav-menu">
                        <div class="nav-item active" id="nav-command-center" onclick="switchView('command-center')">
                            <span class="nav-icon">⌂</span>
                            <span>COMMAND CENTER</span>
                        </div>
                        <div class="nav-item" id="nav-dashboard" onclick="switchView('dashboard')">
                            <span class="nav-icon">◫</span>
                            <span>DASHBOARD</span>
                        </div>
                        <div class="nav-item" id="nav-ai-agents" onclick="switchView('ai-agents')">
                            <span class="nav-icon">⚡</span>
                            <span>AI AGENTS</span>
                        </div>
                        <div class="nav-item" id="nav-trading" onclick="switchView('trading')">
                            <span class="nav-icon">📈</span>
                            <span>TRADING DIVISION</span>
                        </div>
                        <div class="nav-item" id="nav-research" onclick="switchView('research')">
                            <span class="nav-icon">Ⓐ</span>
                            <span>RESEARCH DIVISION</span>
                        </div>
                        <div class="nav-item" id="nav-memory" onclick="switchView('memory')">
                            <span class="nav-icon">🗂</span>
                            <span>MEMORY CORE</span>
                        </div>
                        <div class="nav-item" id="nav-learning" onclick="switchView('learning')">
                            <span class="nav-icon">🎓</span>
                            <span>LEARNING DIVISION</span>
                        </div>
                        <div class="nav-item" id="nav-automation" onclick="switchView('automation')">
                            <span class="nav-icon">⚙</span>
                            <span>AUTOMATION</span>
                        </div>
                        <div class="nav-item" id="nav-voice" onclick="switchView('voice')">
                            <span class="nav-icon">🎙</span>
                            <span>VOICE SYSTEM</span>
                        </div>
                        <div class="nav-item" id="nav-vision" onclick="switchView('vision')">
                            <span class="nav-icon">👁</span>
                            <span>VISION SYSTEM</span>
                        </div>
                        <div class="nav-item" id="nav-plugin" onclick="switchView('plugin')">
                            <span class="nav-icon">🧩</span>
                            <span>PLUGIN SYSTEM</span>
                        </div>
                        <div class="nav-item" id="nav-evolution" onclick="switchView('evolution')">
                            <span class="nav-icon">⨁</span>
                            <span>EVOLUTION ENGINE</span>
                        </div>
                        <div class="nav-item" id="nav-settings" onclick="switchView('settings')">
                            <span class="nav-icon">⚙</span>
                            <span>SETTINGS</span>
                        </div>
                    </div>
                </div>

                <!-- Sidebar Status Card -->
                <div class="sidebar-status-card">
                    <div class="status-left">
                        <span class="status-badge-title">ZOHRA STATUS</span>
                        <div class="status-state-live">
                            <span style="font-size:10px;">🛡️</span> ONLINE
                        </div>
                    </div>
                    <div class="health-ring-box" title="System Health: 98% Optimal">
                        <svg class="health-ring-svg">
                            <circle class="health-ring-bg" cx="22" cy="22" r="16"></circle>
                            <circle class="health-ring-val" cx="22" cy="22" r="16" id="health-ring-circle"></circle>
                        </svg>
                        <span class="health-text-inner" id="health-ring-txt">98%</span>
                    </div>
                </div>
            </nav>

            <!-- ─── CENTER: WORKSPACE PANELS ─── -->

            <!-- 1. LANDING VIEW: COMMAND CENTER (Matches Reference Image) -->
            <main class="os-center workspace-view active" id="view-command-center">
                <!-- Three.js Celestial Sparkle Canvas -->
                <canvas id="celestial-particle-canvas"></canvas>

                <!-- Greeting HUD (Top-Left) -->
                <div class="greeting-hud">
                    <div class="greeting-sub">GOOD EVENING,</div>
                    <div class="greeting-name" id="hud-user-name">KNIGHT</div>
                    <div class="greeting-prompt">How can I assist you today?</div>
                </div>

                <!-- 3D Molecular Hologram Stage (Zero Direct Images) -->
                <div class="central-hologram-stage" id="zohra-hologram-stage">
                    <canvas id="zohra-hologram-canvas"></canvas>
                    <div class="hologram-status-pill" id="hologram-voice-indicator" style="pointer-events: auto; cursor: pointer;" onclick="toggleTalkingDemo(5)" title="Click to talk with Zohra">
                        <span class="holo-dot"></span>
                        <span id="holo-speech-state">HOLOGRAPHIC QUANTUM CORE // IDLE</span>
                        <span style="border-left: 1px solid rgba(212,175,55,0.3); padding-left: 8px; color: var(--gold-bright); font-weight: 700;">[ CLICK TO TALK ]</span>
                    </div>
                </div>

                <!-- Bottom 5 Summary Cards -->
                <div class="bottom-cards-grid">
                    <!-- 1. TRADING DIVISION -->
                    <div class="summary-card" onclick="switchView('trading')">
                        <div class="card-hdr">
                            <span>TRADING DIVISION</span>
                            <span>⋮</span>
                        </div>
                        <div class="card-metric-label">LIVE ACCOUNT VALUE</div>
                        <div class="card-metric-val" id="sc-trading-val">$738.56</div>
                        <div class="card-metric-sub">
                            <span class="sub-win" id="sc-trading-pct">+20.7%</span>
                            <!-- Mini Sparkline -->
                            <svg class="sparkline-svg" viewBox="0 0 60 20">
                                <path d="M0,16 Q15,10 30,12 T60,2" fill="none" stroke="#00ffcc" stroke-width="2" stroke-linecap="round"></path>
                            </svg>
                        </div>
                    </div>

                    <!-- 2. RESEARCH DIVISION -->
                    <div class="summary-card" onclick="switchView('research')">
                        <div class="card-hdr">
                            <span>RESEARCH DIVISION</span>
                            <span>⋮</span>
                        </div>
                        <div class="card-metric-label">ACTIVE RESEARCH</div>
                        <div class="card-metric-val" id="sc-research-val">14</div>
                        <div class="card-metric-sub" style="color:var(--text-muted);">
                            PAPERS ANALYZED: <strong style="color:#fff;" id="sc-research-sub">128</strong>
                        </div>
                    </div>

                    <!-- 3. MEMORY CORE -->
                    <div class="summary-card" onclick="switchView('memory')">
                        <div class="card-hdr">
                            <span>MEMORY CORE</span>
                            <span>⋮</span>
                        </div>
                        <div class="card-metric-label">TOTAL MEMORIES</div>
                        <div class="card-metric-val" id="sc-memory-val">4,325</div>
                        <div class="card-metric-sub" style="color:var(--text-muted);">
                            RETENTION: <strong style="color:var(--gold-bright);" id="sc-memory-sub">98.7%</strong>
                        </div>
                    </div>

                    <!-- 4. LEARNING DIVISION -->
                    <div class="summary-card" onclick="switchView('learning')">
                        <div class="card-hdr">
                            <span>LEARNING DIVISION</span>
                            <span>⋮</span>
                        </div>
                        <div class="card-metric-label">MODEL ACCURACY</div>
                        <div class="card-metric-val" id="sc-learning-val">77.2%</div>
                        <div class="card-metric-sub" style="color:var(--text-muted);">
                            LEARNING: <strong style="color:var(--gold-light);" id="sc-learning-sub">78.3%</strong>
                        </div>
                    </div>

                    <!-- 5. EVOLUTION ENGINE -->
                    <div class="summary-card" onclick="switchView('evolution')">
                        <div class="card-hdr">
                            <span>EVOLUTION ENGINE</span>
                            <span>⋮</span>
                        </div>
                        <div class="card-metric-label">CURRENT VERSION</div>
                        <div class="card-metric-val" style="font-size:16px;" id="sc-evolution-val">Z-OS 1.7.3</div>
                        <div class="card-metric-sub" style="color:var(--text-muted);">
                            PROGRESS: <strong style="color:var(--gold-bright);" id="sc-evolution-sub">62.4%</strong>
                        </div>
                    </div>
                </div>
            </main>

            <!-- 2. TRADING DIVISION WORKSPACE VIEW -->
            <section class="workspace-view" id="view-trading">
                <div class="table-panel">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <h2 style="font-family:'Outfit';font-size:20px;color:var(--gold-bright);">📈 TRADING DIVISION // LIVE ACCOUNTS WORKSPACE</h2>
                        <div>
                            <button class="view-agents-btn" style="width:auto;padding:6px 14px;display:inline-block;" onclick="closeAllPositions()">CLOSE ALL TRADES</button>
                        </div>
                    </div>
                    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:14px;">
                        <div style="background:rgba(0,0,0,0.4);padding:12px;border-radius:6px;border:1px solid var(--gold-border);">
                            <div style="font-size:10px;color:var(--text-muted);">BALANCE</div>
                            <div style="font-size:18px;font-weight:900;color:#fff;" id="td-balance">$600.00</div>
                        </div>
                        <div style="background:rgba(0,0,0,0.4);padding:12px;border-radius:6px;border:1px solid var(--gold-border);">
                            <div style="font-size:10px;color:var(--text-muted);">EQUITY</div>
                            <div style="font-size:18px;font-weight:900;color:var(--gold-bright);" id="td-equity">$738.56</div>
                        </div>
                        <div style="background:rgba(0,0,0,0.4);padding:12px;border-radius:6px;border:1px solid var(--gold-border);">
                            <div style="font-size:10px;color:var(--text-muted);">TODAY'S NET REALIZED P&L</div>
                            <div style="font-size:18px;font-weight:900;color:var(--green-emerald);" id="td-pnl">+$153.32</div>
                        </div>
                        <div style="background:rgba(0,0,0,0.4);padding:12px;border-radius:6px;border:1px solid var(--gold-border);">
                            <div style="font-size:10px;color:var(--text-muted);">OPEN POSITIONS</div>
                            <div style="font-size:18px;font-weight:900;color:#fff;" id="td-positions">0</div>
                        </div>
                    </div>
                </div>

                <!-- Open Positions Table -->
                <div class="table-panel">
                    <h3 style="font-size:14px;color:var(--gold-light);letter-spacing:1px;text-transform:uppercase;">OPEN POSITIONS</h3>
                    <table class="os-table">
                        <thead>
                            <tr>
                                <th>Ticket</th>
                                <th>Account</th>
                                <th>Symbol</th>
                                <th>Type</th>
                                <th>Volume</th>
                                <th>Open Price</th>
                                <th>Current</th>
                                <th>SL</th>
                                <th>TP</th>
                                <th>Floating PnL</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody id="trading-positions-tbody">
                            <tr><td colspan="11" style="text-align:center;color:var(--text-muted);padding:18px;">No open positions in MT5 fleet. System scanning for high-probability setups.</td></tr>
                        </tbody>
                    </table>
                </div>

                <!-- Trade History Table -->
                <div class="table-panel">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <h3 style="font-size:14px;color:var(--gold-light);letter-spacing:1px;text-transform:uppercase;">CLOSED TRADE EXECUTIONS & JOURNAL</h3>
                        <button class="view-agents-btn" style="width:auto;padding:4px 10px;" onclick="exportJournalCSV()">EXPORT CSV</button>
                    </div>
                    <table class="os-table">
                        <thead>
                            <tr>
                                <th>Close Time</th>
                                <th>Ticket</th>
                                <th>Symbol</th>
                                <th>Type</th>
                                <th>Entry</th>
                                <th>Exit</th>
                                <th>P&L ($)</th>
                                <th>Strategy</th>
                                <th>Exit Reason</th>
                            </tr>
                        </thead>
                        <tbody id="trading-history-tbody">
                            <!-- Populated via JS from trades DB -->
                        </tbody>
                    </table>
                </div>
            </section>

            <!-- 3. AI AGENTS VIEW -->
            <section class="workspace-view" id="view-ai-agents">
                <div class="table-panel">
                    <h2 style="font-family:'Outfit';font-size:20px;color:var(--gold-bright);">⚡ AI AGENT SWARM DIRECTORY (17 AGENTS)</h2>
                    <p style="font-size:12px;color:var(--text-muted);margin:4px 0 16px;">Real specialized cognitive processes running within the ZOHRA intelligence core.</p>
                    <div style="display:grid;grid-template-columns:repeat(auto-fill, minmax(260px, 1fr));gap:12px;" id="agents-cards-grid">
                        <!-- Populated by JS -->
                    </div>
                </div>
            </section>

            <!-- 4. DASHBOARD & CONSENSUS VIEW -->
            <section class="workspace-view" id="view-dashboard">
                <div class="table-panel">
                    <h2 style="font-family:'Outfit';font-size:20px;color:var(--gold-bright);">◫ 15-STRATEGY DIRECTIONAL CONSENSUS RADAR</h2>
                    <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(180px, 1fr));gap:12px;margin-top:14px;" id="dash-consensus-grid">
                        <!-- Populated by JS -->
                    </div>
                </div>
            </section>

            <!-- 5. OTHER DIVISIONS (Placeholders with real data) -->
            <section class="workspace-view" id="view-research">
                <div class="table-panel">
                    <h2 style="font-family:'Outfit';font-size:20px;color:var(--gold-bright);">Ⓐ RESEARCH DIVISION // NEWS & MACRO RADAR</h2>
                    <p style="font-size:12px;color:var(--text-muted);margin-top:6px;">14 Active tracking assets with real-time news filter and central bank sentiment integration.</p>
                    <div id="research-events-list" style="margin-top:16px;">
                        <div style="padding:12px;background:rgba(0,0,0,0.3);border:1px solid var(--gold-border);border-radius:6px;margin-bottom:8px;">
                            <strong>FED Interest Rate & FOMC Minutes Monitor</strong> — Status: <span style="color:var(--green-emerald);">Clear (No blackout)</span>
                        </div>
                        <div style="padding:12px;background:rgba(0,0,0,0.3);border:1px solid var(--gold-border);border-radius:6px;margin-bottom:8px;">
                            <strong>ECB Monetary Policy & Eurozone CPI</strong> — Status: <span style="color:var(--green-emerald);">Clear</span>
                        </div>
                    </div>
                </div>
            </section>

            <section class="workspace-view" id="view-memory">
                <div class="table-panel">
                    <h2 style="font-family:'Outfit';font-size:20px;color:var(--gold-bright);">🗂 MEMORY CORE // VECTOR VAULT</h2>
                    <p style="font-size:12px;color:var(--text-muted);margin-top:6px;">4,325 Verified stored vectors (308 Chroma embeddings + 2,776 metadata records + 1,549 market memory nodes).</p>
                    <div style="margin-top:16px;">
                        <input type="text" placeholder="Semantic memory search..." style="width:100%;padding:10px;background:rgba(0,0,0,0.5);border:1px solid var(--gold-border);color:#fff;border-radius:6px;">
                    </div>
                </div>
            </section>

            <section class="workspace-view" id="view-learning">
                <div class="table-panel">
                    <h2 style="font-family:'Outfit';font-size:20px;color:var(--gold-bright);">🎓 LEARNING DIVISION // SETUP CALIBRATION LAB</h2>
                    <p style="font-size:12px;color:var(--text-muted);margin-top:6px;">232,658 Historical setup evaluations with 77.2% high-conviction pattern precision.</p>
                </div>
            </section>

            <section class="workspace-view" id="view-settings">
                <div class="table-panel">
                    <h2 style="font-family:'Outfit';font-size:20px;color:var(--gold-bright);">⚙ SYSTEM & RISK CONFIGURATION</h2>
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px;">
                        <div>
                            <label style="font-size:11px;color:var(--text-muted);">RISK PER TRADE (%)</label>
                            <input type="number" value="1.0" step="0.1" style="width:100%;padding:8px;background:#111;border:1px solid var(--gold-border);color:#fff;border-radius:4px;margin-top:4px;">
                        </div>
                        <div>
                            <label style="font-size:11px;color:var(--text-muted);">MAX OPEN POSITIONS PER ACCOUNT</label>
                            <input type="number" value="3" style="width:100%;padding:8px;background:#111;border:1px solid var(--gold-border);color:#fff;border-radius:4px;margin-top:4px;">
                        </div>
                    </div>
                </div>
            </section>

            <!-- ─── RIGHT COLUMN ─── -->
            <aside class="os-right">
                <!-- 1. AI AGENT NETWORK -->
                <div class="panel-box">
                    <div class="panel-box-hdr">
                        <span>AI AGENT NETWORK</span>
                        <span>⋮</span>
                    </div>
                    <div class="agent-network-row">
                        <!-- Network SVG graph with central Z -->
                        <div class="network-svg-box">
                            <svg class="network-svg" viewBox="0 0 100 100">
                                <!-- Lines -->
                                <line x1="50" y1="50" x2="20" y2="20" stroke="rgba(0,255,204,0.4)" stroke-width="1.2"></line>
                                <line x1="50" y1="50" x2="80" y2="20" stroke="rgba(0,255,204,0.4)" stroke-width="1.2"></line>
                                <line x1="50" y1="50" x2="85" y2="55" stroke="rgba(0,255,204,0.4)" stroke-width="1.2"></line>
                                <line x1="50" y1="50" x2="65" y2="85" stroke="rgba(255,170,0,0.4)" stroke-width="1.2"></line>
                                <line x1="50" y1="50" x2="30" y2="85" stroke="rgba(0,255,204,0.4)" stroke-width="1.2"></line>
                                <line x1="50" y1="50" x2="15" y2="55" stroke="rgba(0,255,204,0.4)" stroke-width="1.2"></line>
                                <!-- Satellite Nodes -->
                                <circle cx="20" cy="20" r="4" fill="#00ffcc"></circle>
                                <circle cx="80" cy="20" r="4" fill="#00ffcc"></circle>
                                <circle cx="85" cy="55" r="4" fill="#00ffcc"></circle>
                                <circle cx="65" cy="85" r="4" fill="#ffaa00"></circle>
                                <circle cx="30" cy="85" r="4" fill="#00ffcc"></circle>
                                <circle cx="15" cy="55" r="4" fill="#00ffcc"></circle>
                                <!-- Central Z Node -->
                                <circle cx="50" cy="50" r="14" fill="#07080e" stroke="#d4af37" stroke-width="1.5"></circle>
                                <text x="50" y="55" text-anchor="middle" font-family="'Outfit'" font-size="12" font-weight="900" fill="#ffd700">Z</text>
                            </svg>
                        </div>
                        <div class="network-stats-list">
                            <div class="net-stat-item"><span>CORE</span><strong id="agent-stat-core">02</strong></div>
                            <div class="net-stat-item"><span>ACTIVE</span><strong id="agent-stat-active" style="color:var(--green-emerald);">12</strong></div>
                            <div class="net-stat-item"><span>BUSY</span><strong id="agent-stat-busy" style="color:var(--amber-warn);">02</strong></div>
                            <div class="net-stat-item"><span>OFFLINE</span><strong id="agent-stat-offline">00</strong></div>
                        </div>
                    </div>
                    <button class="view-agents-btn" onclick="switchView('ai-agents')">VIEW AGENTS</button>
                </div>

                <!-- 2. SYSTEM PERFORMANCE -->
                <div class="panel-box">
                    <div class="panel-box-hdr">
                        <span>SYSTEM PERFORMANCE</span>
                        <span>⋮</span>
                    </div>
                    <div class="rings-row">
                        <!-- CPU -->
                        <div class="ring-item">
                            <div class="ring-container">
                                <svg class="ring-svg">
                                    <circle class="ring-bg-circle" cx="29" cy="29" r="22"></circle>
                                    <circle class="ring-val-circle" cx="29" cy="29" r="22" id="cpu-ring-circle" stroke-dashoffset="76"></circle>
                                </svg>
                                <span class="ring-pct-txt" id="cpu-pct-txt">24%</span>
                            </div>
                            <span class="ring-lbl">CPU</span>
                        </div>
                        <!-- GPU (Truthful) -->
                        <div class="ring-item" title="Host graphics: Integrated GPU">
                            <div class="ring-container">
                                <svg class="ring-svg">
                                    <circle class="ring-bg-circle" cx="29" cy="29" r="22"></circle>
                                    <circle class="ring-val-circle" cx="29" cy="29" r="22" stroke="rgba(255,255,255,0.2)" stroke-dashoffset="100"></circle>
                                </svg>
                                <span class="ring-pct-txt" style="font-size:9px;color:var(--text-muted);" id="gpu-pct-txt">N/A</span>
                            </div>
                            <span class="ring-lbl">GPU</span>
                        </div>
                        <!-- RAM -->
                        <div class="ring-item">
                            <div class="ring-container">
                                <svg class="ring-svg">
                                    <circle class="ring-bg-circle" cx="29" cy="29" r="22"></circle>
                                    <circle class="ring-val-circle" cx="29" cy="29" r="22" id="ram-ring-circle" stroke-dashoffset="32"></circle>
                                </svg>
                                <span class="ring-pct-txt" id="ram-pct-txt">68%</span>
                            </div>
                            <span class="ring-lbl">RAM</span>
                        </div>
                    </div>
                </div>

                <!-- 3. ACTIVE OPERATIONS -->
                <div class="panel-box">
                    <div class="panel-box-hdr">
                        <span>ACTIVE OPERATIONS</span>
                        <span>⋮</span>
                    </div>
                    <div class="ops-list">
                        <div class="op-item">
                            <div class="op-name"><span class="op-dot"></span> Market Analysis</div>
                            <span class="op-state">Running</span>
                        </div>
                        <div class="op-item">
                            <div class="op-name"><span class="op-dot"></span> News Research</div>
                            <span class="op-state">Running</span>
                        </div>
                        <div class="op-item">
                            <div class="op-name"><span class="op-dot"></span> Memory Consolidation</div>
                            <span class="op-state">Running</span>
                        </div>
                        <div class="op-item">
                            <div class="op-name"><span class="op-dot amber"></span> Learning Module</div>
                            <span class="op-state training">Training</span>
                        </div>
                        <div class="op-item">
                            <div class="op-name"><span class="op-dot"></span> Voice Assistant</div>
                            <span class="op-state">Listening</span>
                        </div>
                    </div>
                </div>

                <!-- 4. ZOHRA VOICE -->
                <div class="panel-box">
                    <div class="panel-box-hdr">
                        <span>ZOHRA VOICE</span>
                        <span>⋮</span>
                    </div>
                    <div class="waveform-box">
                        <canvas id="voice-canvas"></canvas>
                    </div>
                    <div class="voice-mic-status" onclick="toggleVoiceCapture()">
                        <span>🎙</span>
                        <span id="voice-status-txt">Listening... (Click to toggle mic)</span>
                    </div>
                </div>
            </aside>
        </div>
    </div>

    <!-- ═══ APPLICATION JAVASCRIPT LOGIC ═══ -->
    <script>
        let currentView = 'command-center';
        let currentAccount = 'all';
        let audioContext = null;
        let micStream = null;
        let isListening = true;

        // View Switching
        function switchView(viewId) {
            currentView = viewId;
            document.querySelectorAll('.workspace-view').forEach(v => v.classList.remove('active'));
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

            const targetView = document.getElementById(`view-${viewId}`) || document.getElementById('view-command-center');
            targetView.classList.add('active');

            const targetNav = document.getElementById(`nav-${viewId}`) || document.getElementById('nav-command-center');
            targetNav.classList.add('active');

            if (viewId === 'trading') loadTradingData();
            if (viewId === 'ai-agents') loadAgentsList();
            if (viewId === 'dashboard') loadDashboardConsensus();
        }

        // Account Selection Change
        function onAccountSelectorChange(accId) {
            currentAccount = accId;
            fetchTelemetryData();
            if (currentView === 'trading') loadTradingData();
        }

        // Real-time Clock
        function updateClock() {
            const now = new Date();
            const timeStr = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true });
            const el = document.getElementById('top-system-time');
            if (el) el.textContent = timeStr;
        }
        setInterval(updateClock, 1000);
        updateClock();

        // ─── GOLDEN CONSTELLATION CANVAS ───
        function initCelestialCanvas() {
            const canvas = document.getElementById('celestial-particle-canvas');
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            let w, h;
            function resize() {
                w = canvas.width = canvas.clientWidth;
                h = canvas.height = canvas.clientHeight;
            }
            resize();
            window.addEventListener('resize', resize);

            const numStars = 140;
            const stars = [];
            for (let i = 0; i < numStars; i++) {
                stars.push({
                    x: Math.random() * (w || 1000),
                    y: Math.random() * (h || 700),
                    vx: (Math.random() - 0.5) * 0.25,
                    vy: (Math.random() - 0.5) * 0.25,
                    radius: Math.random() * 1.5 + 0.6,
                    alpha: Math.random() * 0.65 + 0.35,
                    pulse: Math.random() * Math.PI * 2,
                    pulseSpeed: 0.015 + Math.random() * 0.025
                });
            }

            // Subtle mouse parallax
            window.addEventListener('mousemove', (e) => {
                const pImg = document.getElementById('zohra-portrait-img');
                if (pImg) {
                    const nx = (e.clientX / window.innerWidth - 0.5) * 12;
                    const ny = (e.clientY / window.innerHeight - 0.5) * 8;
                    pImg.style.transform = `translate(${nx}px, ${ny}px)`;
                }
            });

            function anim() {
                requestAnimationFrame(anim);
                if (!w || !h) resize();
                ctx.clearRect(0, 0, w, h);

                // Draw constellation filaments
                for (let i = 0; i < numStars; i++) {
                    const s1 = stars[i];
                    for (let j = i + 1; j < numStars; j++) {
                        const s2 = stars[j];
                        const dx = s1.x - s2.x;
                        const dy = s1.y - s2.y;
                        const dist = Math.sqrt(dx * dx + dy * dy);
                        if (dist < 80) {
                            const lineAlpha = (1 - dist / 80) * 0.12;
                            ctx.strokeStyle = `rgba(212, 175, 55, ${lineAlpha})`;
                            ctx.lineWidth = 0.6;
                            ctx.beginPath();
                            ctx.moveTo(s1.x, s1.y);
                            ctx.lineTo(s2.x, s2.y);
                            ctx.stroke();
                        }
                    }
                }

                // Draw glowing golden stars
                for (let i = 0; i < numStars; i++) {
                    const s = stars[i];
                    s.x += s.vx;
                    s.y += s.vy;
                    if (s.x < 0) s.x = w;
                    if (s.x > w) s.x = 0;
                    if (s.y < 0) s.y = h;
                    if (s.y > h) s.y = 0;

                    s.pulse += s.pulseSpeed;
                    const currentAlpha = s.alpha * (0.6 + 0.4 * Math.sin(s.pulse));

                    // Soft radial glow
                    const grad = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, s.radius * 3.5);
                    grad.addColorStop(0, `rgba(255, 225, 120, ${currentAlpha})`);
                    grad.addColorStop(0.4, `rgba(212, 175, 55, ${currentAlpha * 0.4})`);
                    grad.addColorStop(1, 'rgba(212, 175, 55, 0)');
                    ctx.fillStyle = grad;
                    ctx.beginPath();
                    ctx.arc(s.x, s.y, s.radius * 3.5, 0, Math.PI * 2);
                    ctx.fill();

                    // Core pinpoint
                    ctx.fillStyle = `rgba(255, 245, 200, ${Math.min(1, currentAlpha * 1.5)})`;
                    ctx.beginPath();
                    ctx.arc(s.x, s.y, s.radius, 0, Math.PI * 2);
                    ctx.fill();
                }
            }
            anim();
        }

        // ─── 100% PURE 3D FLOATING MOLECULAR FACE ENGINE (NO RASTER IMAGES) ───
        let holoScene = null, holoCamera = null, holoRenderer = null;
        let holoMoleculesGeo = null;
        let holoBasePos = null;
        let holoCurPos = null;
        let holoRegions = null;
        let holoPhases = null;
        let holoPointCloud = null;
        let holoLines = null;
        let holoMoleculesCount = 0;
        let holoMouthOpen = 0;
        let holoTargetMouthOpen = 0;
        let isHoloSpeaking = false;
        let isMicHooked = false;
        let holoAudioAnalyser = null;
        let holoFreqData = null;
        let holoDemoActive = false;
        let holoDemoTimeout = null;

        function initZohraMolecularHologram() {
            const canvas = document.getElementById('zohra-hologram-canvas');
            if (!canvas || typeof THREE === 'undefined') return;

            holoScene = new THREE.Scene();
            // Perspective camera positioned to view the full floating molecular face
            holoCamera = new THREE.PerspectiveCamera(42, canvas.clientWidth / canvas.clientHeight, 1, 1000);
            holoCamera.position.set(0, 0, 160);

            holoRenderer = new THREE.WebGLRenderer({
                canvas: canvas,
                alpha: true,
                antialias: true,
                powerPreference: 'high-performance'
            });
            holoRenderer.setSize(canvas.clientWidth, canvas.clientHeight);
            holoRenderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

            // Generate radiant glowing molecular sprite
            const atomCanvas = document.createElement('canvas');
            atomCanvas.width = atomCanvas.height = 64;
            const actx = atomCanvas.getContext('2d');
            const grad = actx.createRadialGradient(32, 32, 0, 32, 32, 32);
            grad.addColorStop(0, '#ffffff');                     // Core nucleus: bright white
            grad.addColorStop(0.2, '#fff4b8');                   // Inner halo: warm white-gold
            grad.addColorStop(0.48, '#ffd700');                  // Mantle: vibrant gold
            grad.addColorStop(0.78, 'rgba(212, 175, 55, 0.45)'); // Outer corona: golden amber
            grad.addColorStop(1, 'rgba(212, 175, 55, 0)');       // Falloff: transparent
            actx.fillStyle = grad;
            actx.beginPath();
            actx.arc(32, 32, 32, 0, Math.PI * 2);
            actx.fill();
            const atomTex = new THREE.CanvasTexture(atomCanvas);

            // Fetch the high-density floating molecular face dataset (29,973 pure 3D molecules)
            fetch('/static/zohra_floating_molecules.json')
                .then(res => res.json())
                .then(molecules => {
                    holoMoleculesCount = molecules.length;
                    const N = holoMoleculesCount;

                    holoBasePos = new Float32Array(N * 3);
                    holoCurPos = new Float32Array(N * 3);
                    const colors = new Float32Array(N * 3);
                    holoRegions = new Int8Array(N);
                    holoPhases = new Float32Array(N);

                    for (let i = 0; i < N; i++) {
                        const m = molecules[i];
                        // m: [wx, wy, wz, r, g, b, size, region, phase]
                        holoBasePos[i * 3]     = m[0];
                        holoBasePos[i * 3 + 1] = m[1];
                        holoBasePos[i * 3 + 2] = m[2];

                        holoCurPos[i * 3]     = m[0];
                        holoCurPos[i * 3 + 1] = m[1];
                        holoCurPos[i * 3 + 2] = m[2];

                        colors[i * 3]     = m[3] / 255;
                        colors[i * 3 + 1] = m[4] / 255;
                        colors[i * 3 + 2] = m[5] / 255;

                        holoRegions[i] = m[7];
                        holoPhases[i] = m[8];
                    }

                    holoMoleculesGeo = new THREE.BufferGeometry();
                    holoMoleculesGeo.setAttribute('position', new THREE.BufferAttribute(holoCurPos, 3));
                    holoMoleculesGeo.setAttribute('color', new THREE.BufferAttribute(colors, 3));

                    const pointsMat = new THREE.PointsMaterial({
                        size: 3.3,
                        map: atomTex,
                        vertexColors: true,
                        transparent: true,
                        blending: THREE.AdditiveBlending,
                        depthWrite: false
                    });

                    holoPointCloud = new THREE.Points(holoMoleculesGeo, pointsMat);
                    holoScene.add(holoPointCloud);

                    // Build golden cybernetic constellation bonds connecting nearby nodes
                    const lineIndices = [];
                    const step = 6;
                    for (let i = 0; i < N; i += step) {
                        if (holoRegions[i] === 6) continue;
                        const x1 = holoBasePos[i * 3];
                        const y1 = holoBasePos[i * 3 + 1];
                        const z1 = holoBasePos[i * 3 + 2];

                        let connections = 0;
                        for (let j = i + step; j < Math.min(N, i + 160); j += step) {
                            if (holoRegions[j] === 6) continue;
                            const dx = x1 - holoBasePos[j * 3];
                            const dy = y1 - holoBasePos[j * 3 + 1];
                            const dz = z1 - holoBasePos[j * 3 + 2];
                            const dist = Math.sqrt(dx*dx + dy*dy + dz*dz);
                            if (dist < 8.5) {
                                lineIndices.push(i, j);
                                connections++;
                                if (connections >= 3) break;
                            }
                        }
                    }

                    const linesGeo = new THREE.BufferGeometry();
                    linesGeo.setAttribute('position', holoMoleculesGeo.attributes.position);
                    linesGeo.setIndex(lineIndices);

                    holoLines = new THREE.LineSegments(linesGeo, new THREE.LineBasicMaterial({
                        color: 0xffd700,
                        transparent: true,
                        opacity: 0.28,
                        blending: THREE.AdditiveBlending
                    }));
                    holoScene.add(holoLines);

                    console.log(`🌌 100% Pure Floating 3D Molecular Face initialized with ${N} golden molecules & ${lineIndices.length / 2} lattice bonds!`);
                });

            // Click canvas to trigger voice interaction
            canvas.addEventListener('click', () => {
                toggleTalkingDemo(5);
            });

            // Animation loop with 3D Floating Physics
            let clock = new THREE.Clock();
            function render() {
                requestAnimationFrame(render);
                const t = clock.getElapsedTime();

                // 1. Audio and talking detection
                if (holoAudioAnalyser && holoFreqData) {
                    holoAudioAnalyser.getByteFrequencyData(holoFreqData);
                    let sum = 0;
                    for (let i = 2; i < 16; i++) sum += holoFreqData[i];
                    const vol = (sum / 14) / 128.0;
                    if (vol > 0.07) {
                        isHoloSpeaking = true;
                        const phoneme = Math.sin(t * 16.0) * 0.4 + 0.6;
                        holoTargetMouthOpen = Math.min(1.0, vol * 2.2) * phoneme;
                    } else if (!holoDemoActive) {
                        isHoloSpeaking = false;
                        holoTargetMouthOpen = 0;
                    }
                } else if (holoDemoActive) {
                    // Natural speech syllable cadence (~3.5 Hz)
                    const syllable = Math.sin(t * 14.5) * 0.5 + 0.5;
                    const vowel = Math.cos(t * 8.5) * 0.35 + 0.65;
                    holoTargetMouthOpen = syllable * vowel;
                } else {
                    holoTargetMouthOpen = 0;
                }

                // Smooth mouth interpolation
                holoMouthOpen += (holoTargetMouthOpen - holoMouthOpen) * 0.35;

                // 2. 3D Floating Physics & Speech Articulation
                if (holoMoleculesGeo && holoBasePos && holoCurPos) {
                    const pos = holoMoleculesGeo.attributes.position.array;
                    const N = holoMoleculesCount;
                    const mouthOpen = holoMouthOpen;

                    for (let i = 0; i < N; i++) {
                        const bx = holoBasePos[i * 3];
                        const by = holoBasePos[i * 3 + 1];
                        const bz = holoBasePos[i * 3 + 2];
                        const reg = holoRegions[i];
                        const ph = holoPhases[i];

                        // Organic 3D Floating Drift
                        let fx = 0, fy = 0, fz = 0;
                        if (reg === 5) {
                            // Hair curls float with gentle zero-gravity harmonic waves
                            fx = Math.sin(t * 1.05 + ph) * 2.2;
                            fy = Math.cos(t * 0.82 + ph * 1.1) * 2.6;
                            fz = Math.sin(t * 0.95 + ph * 0.7) * 2.0;
                        } else if (reg === 6) {
                            // Ambient cosmic dust: floating brownian drift
                            fx = Math.sin(t * 0.45 + ph) * 3.8;
                            fy = Math.cos(t * 0.4 + ph) * 3.8;
                            fz = Math.sin(t * 0.55 + ph * 1.3) * 3.5;
                        } else if (reg === 4) {
                            // Eyes: stable gaze, very subtle floating micro-drift
                            fx = Math.sin(t * 0.65 + ph) * 0.25;
                            fy = Math.cos(t * 0.55 + ph) * 0.3;
                            fz = Math.sin(t * 0.45 + ph) * 0.2;
                        } else {
                            // Facial core / skin: subtle lifelike breathing floating wave
                            fx = Math.sin(t * 0.75 + ph) * 0.6;
                            fy = Math.cos(t * 0.7 + by * 0.04) * 0.9;
                            fz = Math.sin(t * 0.85 + bx * 0.04) * 0.7;
                        }

                        // Speech Articulation ONLY when speaking (mouthOpen > 0)
                        let spkX = 0, spkY = 0, spkZ = 0;
                        if (mouthOpen > 0.001) {
                            if (reg === 2) {
                                // Lower lip: opens downward and slightly forward
                                spkY = -mouthOpen * 7.5;
                                spkZ = mouthOpen * 2.2;
                            } else if (reg === 3) {
                                // Chin / jaw: drops naturally with lower lip
                                spkY = -mouthOpen * 4.8;
                                spkZ = mouthOpen * 1.4;
                            } else if (reg === 1) {
                                // Upper lip: arches slightly upward
                                spkY = mouthOpen * 2.0;
                                spkZ = mouthOpen * 0.5;
                            }
                        }

                        pos[i * 3]     = bx + fx + spkX;
                        pos[i * 3 + 1] = by + fy + spkY;
                        pos[i * 3 + 2] = bz + fz + spkZ;
                    }

                    holoMoleculesGeo.attributes.position.needsUpdate = true;
                }

                // 3. Gentle whole-head floating levitation & subtle mouse parallax
                if (holoPointCloud) {
                    holoPointCloud.position.y = Math.sin(t * 0.6) * 1.6;
                    holoPointCloud.position.x = Math.cos(t * 0.45) * 1.0;
                    holoPointCloud.rotation.y = Math.sin(t * 0.35) * 0.05;
                }
                if (holoLines) {
                    holoLines.position.y = holoPointCloud.position.y;
                    holoLines.position.x = holoPointCloud.position.x;
                    holoLines.rotation.y = holoPointCloud.rotation.y;
                }

                // 4. Update status pill
                const pillState = document.getElementById('holo-speech-state');
                if (pillState) {
                    if (isHoloSpeaking || holoDemoActive) {
                        pillState.textContent = 'HOLOGRAPHIC QUANTUM CORE // SPEAKING';
                        pillState.style.color = 'var(--gold-bright)';
                    } else if (isMicHooked) {
                        pillState.textContent = 'HOLOGRAPHIC QUANTUM CORE // LISTENING';
                        pillState.style.color = 'var(--green-emerald)';
                    } else {
                        pillState.textContent = 'HOLOGRAPHIC QUANTUM CORE // IDLE (FLOATING)';
                        pillState.style.color = 'var(--gold-light)';
                    }
                }

                holoRenderer.render(holoScene, holoCamera);
            }
            render();

            window.addEventListener('resize', () => {
                if (!canvas.clientWidth || !canvas.clientHeight) return;
                holoCamera.aspect = canvas.clientWidth / canvas.clientHeight;
                holoCamera.updateProjectionMatrix();
                holoRenderer.setSize(canvas.clientWidth, canvas.clientHeight);
            });
        }

        function toggleTalkingDemo(durationSec = 25) {
            if (holoDemoActive) {
                holoDemoActive = false;
                isHoloSpeaking = false;
                clearTimeout(holoDemoTimeout);
                if ('speechSynthesis' in window) window.speechSynthesis.cancel();
                return;
            }
            holoDemoActive = true;
            isHoloSpeaking = true;

            if ('speechSynthesis' in window) {
                window.speechSynthesis.cancel();
                const utter = new SpeechSynthesisUtterance("Knight, all trading divisions and molecular intelligence circuits are active and synchronized.");
                utter.rate = 1.05;
                utter.pitch = 1.15;
                utter.onend = () => {
                    holoDemoActive = false;
                    isHoloSpeaking = false;
                };
                window.speechSynthesis.speak(utter);
            }

            clearTimeout(holoDemoTimeout);
            holoDemoTimeout = setTimeout(() => {
                holoDemoActive = false;
                isHoloSpeaking = false;
            }, durationSec * 1000);
        }

        // ─── GOLDEN VOICE WAVEFORM SIMULATOR & MIC HOOK ───
        async function connectMicrophoneStream() {
            try {
                if (!holoAudioCtx) {
                    holoAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
                }
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                const source = holoAudioCtx.createMediaStreamSource(stream);
                holoAnalyser = holoAudioCtx.createAnalyser();
                holoAnalyser.fftSize = 64;
                source.connect(holoAnalyser);
                holoFreqData = new Uint8Array(holoAnalyser.frequencyBinCount);
                console.log("🎤 Real microphone hooked directly to Zohra molecular hologram!");
                return true;
            } catch (err) {
                console.warn("Microphone permission or hardware not active:", err);
                return false;
            }
        }

        function initVoiceWaveform() {
            const canvas = document.getElementById('voice-canvas');
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            let t = 0;

            function drawWave() {
                requestAnimationFrame(drawWave);
                t += 0.05;
                const w = canvas.width = canvas.clientWidth;
                const h = canvas.height = canvas.clientHeight;
                ctx.clearRect(0, 0, w, h);

                ctx.lineWidth = 1.5;
                ctx.strokeStyle = '#ffd700';
                ctx.shadowColor = 'rgba(212, 175, 55, 0.4)';
                ctx.shadowBlur = 8;
                ctx.beginPath();

                const bars = 48;
                const barWidth = w / bars;
                for (let i = 0; i < bars; i++) {
                    const distFromCenter = Math.abs(i - bars / 2) / (bars / 2);
                    const envelope = Math.cos(distFromCenter * Math.PI * 0.5);
                    const activeAmp = (isListening || isHoloSpeaking) ? (Math.sin(t * 2.5 + i * 0.4) * 0.5 + 0.5) * 18 * envelope : 2.5;
                    
                    const x = i * barWidth + barWidth * 0.5;
                    const y1 = h * 0.5 - activeAmp;
                    const y2 = h * 0.5 + activeAmp;
                    ctx.moveTo(x, y1);
                    ctx.lineTo(x, y2);
                }
                ctx.stroke();
            }
            drawWave();
        }

        async function toggleVoiceCapture() {
            isListening = !isListening;
            const el = document.getElementById('voice-status-txt');
            if (isListening) {
                if (el) el.textContent = 'Listening... (Talk now to move hologram)';
                await connectMicrophoneStream();
                // Also trigger conversational greeting
                toggleTalkingDemo(4);
            } else {
                if (el) el.textContent = 'Microphone Muted (Click to talk)';
                window._demoTalkingActive = false;
                isHoloSpeaking = false;
            }
        }

        // ─── REAL TELEMETRY INGESTION ───
        async function fetchTelemetryData() {
            try {
                const res = await fetch(`/api/v1/os/telemetry?account=${currentAccount}`);
                if (!res.ok) return;
                const data = await res.json();

                // 1. Trading Division Summary Card
                const td = data.trading_division;
                document.getElementById('sc-trading-val').textContent = `$${td.equity.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                const pctEl = document.getElementById('sc-trading-pct');
                pctEl.textContent = `${td.daily_pnl >= 0 ? '+' : ''}$${td.daily_pnl.toFixed(2)} (${td.pnl_pct >= 0 ? '+' : ''}${td.pnl_pct}%)`;
                pctEl.className = td.daily_pnl >= 0 ? 'sub-win' : 'sub-loss';

                // Trading View numbers
                const tdBal = document.getElementById('td-balance');
                if (tdBal) tdBal.textContent = `$${td.balance.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                const tdEq = document.getElementById('td-equity');
                if (tdEq) tdEq.textContent = `$${td.equity.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                const tdPnl = document.getElementById('td-pnl');
                if (tdPnl) {
                    tdPnl.textContent = `${td.daily_pnl >= 0 ? '+' : ''}$${td.daily_pnl.toFixed(2)}`;
                    tdPnl.style.color = td.daily_pnl >= 0 ? 'var(--green-emerald)' : 'var(--red-ruby)';
                }
                const tdPos = document.getElementById('td-positions');
                if (tdPos) tdPos.textContent = td.open_positions;

                // 2. Research Division
                const rd = data.research_division;
                document.getElementById('sc-research-val').textContent = rd.active_research;
                document.getElementById('sc-research-sub').textContent = rd.papers_analyzed_today;

                // 3. Memory Core
                const md = data.memory_core;
                document.getElementById('sc-memory-val').textContent = md.total_memories.toLocaleString();
                document.getElementById('sc-memory-sub').textContent = `${md.long_term_retention_pct}%`;

                // 4. Learning Division
                const ld = data.learning_division;
                document.getElementById('sc-learning-val').textContent = `${ld.model_accuracy_pct}%`;
                document.getElementById('sc-learning-sub').textContent = `${ld.learning_progress_pct}%`;

                // 5. Evolution Engine
                const ed = data.evolution_engine;
                document.getElementById('sc-evolution-val').textContent = ed.current_version;
                document.getElementById('sc-evolution-sub').textContent = `${ed.evolution_progress_pct}%`;

                // 6. System Performance Gauges (Real psutil metrics)
                const sp = data.system_performance;
                updateRingGauge('cpu-ring-circle', 'cpu-pct-txt', sp.cpu_usage_pct);
                updateRingGauge('ram-ring-circle', 'ram-pct-txt', sp.ram_usage_pct);
                document.getElementById('gpu-pct-txt').textContent = sp.gpu_usage;

                // 7. AI Agents Status
                const ag = data.ai_agents;
                document.getElementById('agent-stat-core').textContent = String(ag.core_count).padStart(2, '0');
                document.getElementById('agent-stat-active').textContent = String(ag.active_count).padStart(2, '0');
                document.getElementById('agent-stat-busy').textContent = String(ag.busy_count).padStart(2, '0');
                document.getElementById('agent-stat-offline').textContent = String(ag.offline_count).padStart(2, '0');

            } catch (e) {
                console.warn('Telemetry fetch error:', e);
            }
        }

        function updateRingGauge(circleId, textId, pctVal) {
            const circ = document.getElementById(circleId);
            const txt = document.getElementById(textId);
            if (!circ || !txt) return;

            const radius = 22;
            const circumference = 2 * Math.PI * radius; // ~138.23
            const pct = Math.min(100, Math.max(0, pctVal));
            const offset = circumference - (pct / 100) * circumference;

            circ.style.strokeDasharray = circumference;
            circ.style.strokeDashoffset = offset;
            txt.textContent = `${Math.round(pct)}%`;
        }

        // ─── TRADING WORKSPACE POPULATION ───
        async function loadTradingData() {
            try {
                // Open Positions
                const pRes = await fetch('/api/v1/trades/open');
                if (pRes.ok) {
                    const pData = await pRes.json();
                    const tbody = document.getElementById('trading-positions-tbody');
                    if (tbody && pData.trades && pData.trades.length > 0) {
                        tbody.innerHTML = pData.trades.map(t => `
                            <tr>
                                <td>#${t.ticket || t.trade_id}</td>
                                <td>${t.account_id || 'Account 1'}</td>
                                <td><strong>${t.symbol}</strong></td>
                                <td><span class="${t.direction === 'BUY' ? 'badge-buy' : 'badge-sell'}">${t.direction}</span></td>
                                <td>${t.position_size_lots || t.volume || 0.01}</td>
                                <td>${t.entry_price}</td>
                                <td>${t.current_price || t.entry_price}</td>
                                <td>${t.stop_loss || 'None'}</td>
                                <td>${t.take_profit || 'None'}</td>
                                <td style="color:${(t.profit_loss || 0) >= 0 ? 'var(--green-emerald)' : 'var(--red-ruby)'};font-weight:700;">
                                    ${(t.profit_loss || 0) >= 0 ? '+' : ''}$${(t.profit_loss || 0).toFixed(2)}
                                </td>
                                <td><button class="view-agents-btn" style="width:auto;padding:2px 8px;" onclick="closeSingleTrade(${t.ticket})">CLOSE</button></td>
                            </tr>
                        `).join('');
                    }
                }

                // History
                const hRes = await fetch('/api/v1/trades?limit=25');
                if (hRes.ok) {
                    const hData = await hRes.json();
                    const hbody = document.getElementById('trading-history-tbody');
                    if (hbody && hData.trades && hData.trades.length > 0) {
                        hbody.innerHTML = hData.trades.map(t => `
                            <tr>
                                <td>${(t.timestamp_close || '').substring(0, 19).replace('T', ' ')}</td>
                                <td>#${t.mt5_ticket || t.trade_id}</td>
                                <td><strong>${t.symbol}</strong></td>
                                <td><span class="${t.direction === 'BUY' ? 'badge-buy' : 'badge-sell'}">${t.direction}</span></td>
                                <td>${t.entry_price}</td>
                                <td>${t.exit_price || 'N/A'}</td>
                                <td style="color:${(t.profit_loss || 0) >= 0 ? 'var(--green-emerald)' : 'var(--red-ruby)'};font-weight:700;">
                                    ${(t.profit_loss || 0) >= 0 ? '+' : ''}$${(t.profit_loss || 0).toFixed(2)}
                                </td>
                                <td>${t.strategy || 'Unified'}</td>
                                <td>${t.reason_for_exit || 'TP/SL Hit'}</td>
                            </tr>
                        `).join('');
                    }
                }
            } catch (e) {
                console.warn('Trading data error:', e);
            }
        }

        // Close all positions
        async function closeAllPositions() {
            if (!confirm('CONFIRM EMERGENCY ACTION: Close all open positions across fleet?')) return;
            try {
                const res = await fetch('/api/v1/commands/close-all', { method: 'POST' });
                const d = await res.json();
                alert(`Closed: ${d.positions_closed} positions.`);
                loadTradingData();
                fetchTelemetryData();
            } catch (e) {
                alert('Close all failed: ' + e.message);
            }
        }

        // Export CSV
        function exportJournalCSV() {
            window.open('/api/v1/trades?limit=500', '_blank');
        }

        // AI Agents Swarm
        async function loadAgentsList() {
            try {
                const res = await fetch('/api/v1/os/telemetry');
                if (!res.ok) return;
                const d = await res.json();
                const grid = document.getElementById('agents-cards-grid');
                if (grid && d.ai_agents && d.ai_agents.agents) {
                    grid.innerHTML = d.ai_agents.agents.map(a => `
                        <div style="background:rgba(0,0,0,0.4);border:1px solid var(--gold-border);border-radius:6px;padding:12px;">
                            <div style="display:flex;justify-content:space-between;align-items:center;">
                                <strong style="color:#fff;font-size:13px;">${a.name}</strong>
                                <span style="font-size:10px;color:var(--green-emerald);font-weight:700;">● ${a.status}</span>
                            </div>
                            <div style="font-size:11px;color:var(--gold-light);margin-top:4px;">${a.role}</div>
                            <div style="font-size:10px;color:var(--text-muted);margin-top:6px;">Category: ${a.category}</div>
                        </div>
                    `).join('');
                }
            } catch (e) {
                console.warn('Agents list error:', e);
            }
        }

        // Consensus Radar for Dashboard
        async function loadDashboardConsensus() {
            try {
                const res = await fetch('/api/v1/consensus');
                if (!res.ok) return;
                const d = await res.json();
                const grid = document.getElementById('dash-consensus-grid');
                if (grid && d.consensus) {
                    grid.innerHTML = d.consensus.map(c => `
                        <div style="background:rgba(0,0,0,0.4);border:1px solid var(--gold-border);border-radius:6px;padding:12px;">
                            <div style="display:flex;justify-content:space-between;">
                                <strong style="color:#fff;font-size:16px;">${c.symbol}</strong>
                                <span class="${c.dominant_direction === 'BUY' ? 'badge-buy' : 'badge-sell'}">${c.dominant_direction}</span>
                            </div>
                            <div style="font-size:12px;color:var(--text-muted);margin-top:6px;">
                                Tally: <strong>${c.buy_count} BUY vs ${c.sell_count} SELL</strong>
                            </div>
                            <div style="font-size:11px;color:var(--gold-bright);margin-top:2px;">
                                ${c.confidence || 85}% Confluence
                            </div>
                        </div>
                    `).join('');
                }
            } catch (e) {
                console.warn('Consensus error:', e);
            }
        }

        // Init Sequence
        window.addEventListener('DOMContentLoaded', () => {
            initCelestialCanvas();
            initZohraMolecularHologram();
            initVoiceWaveform();
            fetchTelemetryData();
            loadTradingData();
            setInterval(fetchTelemetryData, 3000); // 3s live polling
        });
    </script>
</body>
</html>
"""

with open("zohra/api/dashboard.html", "w", encoding="utf-8") as f:
    f.write(dashboard_html.strip())

print(f"Generated new ZOHRA AI OS Command Center dashboard.html! Length: {len(dashboard_html):,} chars")
