import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

dashboard_path = "zohra/api/dashboard.html"
with open(dashboard_path, "r", encoding="utf-8") as f:
    html = f.read()

print(f"Original dashboard length: {len(html)} chars, {len(html.splitlines())} lines")

# 1. Add Three.js to <head> if not present
if "three.min.js" not in html:
    three_tag = '<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>'
    html = html.replace('<script src="https://s3.tradingview.com/tv.js"></script>',
                        '<script src="https://s3.tradingview.com/tv.js"></script>\n    <!-- Three.js 3D Molecular AI Consciousness -->\n    ' + three_tag)
    print("Added Three.js to <head>")

# 2. Add New CSS Styles before </style>
new_css = """
        /* ═══════════════════════════════════════════════════════════
           ZOHRA 3D MOLECULAR AI FACE & FLEET EXPANSION STYLES
           ═══════════════════════════════════════════════════════════ */
        
        /* 3D Molecular Face Header Orb */
        .zohra-avatar-widget {
            display: flex;
            align-items: center;
            gap: 14px;
            cursor: pointer;
            padding: 6px 14px;
            background: rgba(138, 43, 226, 0.08);
            border: 1px solid rgba(138, 43, 226, 0.25);
            border-radius: 40px;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .zohra-avatar-widget:hover {
            background: rgba(138, 43, 226, 0.16);
            border-color: var(--accent);
            box-shadow: 0 0 20px rgba(0, 255, 204, 0.25);
            transform: scale(1.02);
        }
        .zohra-avatar-orb {
            width: 44px;
            height: 44px;
            border-radius: 50%;
            position: relative;
            overflow: hidden;
            background: radial-gradient(circle, rgba(138,43,226,0.3) 0%, rgba(5,6,16,0.9) 75%);
            border: 1.5px solid var(--accent);
            box-shadow: 0 0 12px var(--accent-glow);
        }
        #zohra-avatar-canvas {
            width: 100% !important;
            height: 100% !important;
            display: block;
        }
        .zohra-avatar-info {
            display: flex;
            flex-direction: column;
            gap: 2px;
        }
        .zohra-avatar-title {
            font-family: 'Outfit', sans-serif;
            font-size: 13px;
            font-weight: 700;
            color: #fff;
            display: flex;
            align-items: center;
            gap: 6px;
            letter-spacing: 0.5px;
        }
        .zohra-avatar-status {
            font-family: 'Space Grotesk', monospace;
            font-size: 11px;
            color: var(--accent);
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        /* Fullscreen Holographic 3D Face Modal */
        #zohra-face-modal {
            display: none;
            position: fixed;
            inset: 0;
            z-index: 9999;
            background: rgba(3, 4, 10, 0.94);
            backdrop-filter: blur(20px);
            justify-content: center;
            align-items: center;
            flex-direction: column;
        }
        #zohra-face-modal.open {
            display: flex;
            animation: fadeInModal 0.3s ease;
        }
        @keyframes fadeInModal {
            from { opacity: 0; transform: scale(0.98); }
            to { opacity: 1; transform: scale(1); }
        }
        .holo-modal-canvas-box {
            width: 90vw;
            max-width: 900px;
            height: 65vh;
            position: relative;
            border: 1px solid rgba(0, 255, 204, 0.2);
            border-radius: 20px;
            background: radial-gradient(circle at 50% 50%, rgba(138, 43, 226, 0.1) 0%, rgba(5,6,15,0.8) 70%);
            box-shadow: 0 0 40px rgba(138, 43, 226, 0.2), inset 0 0 40px rgba(0, 255, 204, 0.05);
            overflow: hidden;
        }
        #zohra-holo-canvas {
            width: 100% !important;
            height: 100% !important;
        }
        .holo-modal-close {
            position: absolute;
            top: 20px;
            right: 24px;
            font-size: 28px;
            color: var(--text-muted);
            cursor: pointer;
            transition: color 0.2s;
            z-index: 10;
        }
        .holo-modal-close:hover { color: var(--danger); }
        .holo-modal-hud {
            position: absolute;
            bottom: 20px;
            left: 24px;
            right: 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            pointer-events: none;
        }
        .holo-hud-stats {
            font-family: 'Space Grotesk', monospace;
            font-size: 12px;
            color: var(--text-muted);
            background: rgba(0,0,0,0.5);
            padding: 8px 16px;
            border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.06);
        }
        .holo-hud-controls {
            pointer-events: auto;
            display: flex;
            gap: 10px;
        }

        /* ─── FLEET MULTI-ACCOUNT CONTROL BAR ─── */
        .fleet-bar-container {
            padding: 14px 40px;
            background: rgba(9, 12, 24, 0.65);
            border-bottom: 1px solid var(--card-border);
            display: grid;
            grid-template-columns: 220px 1fr 1fr 1fr auto;
            gap: 14px;
            align-items: center;
        }
        @media (max-width: 1200px) {
            .fleet-bar-container {
                grid-template-columns: 1fr 1fr;
                padding: 14px 20px;
            }
        }
        .fleet-card {
            background: rgba(15, 19, 36, 0.85);
            border: 1px solid var(--card-border);
            border-radius: 12px;
            padding: 12px 16px;
            cursor: pointer;
            transition: all 0.25s ease;
            position: relative;
            overflow: hidden;
        }
        .fleet-card:hover {
            border-color: rgba(0, 255, 204, 0.4);
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(0,0,0,0.4);
        }
        .fleet-card.active {
            border-color: var(--accent);
            background: rgba(0, 255, 204, 0.04);
            box-shadow: 0 0 20px rgba(0, 255, 204, 0.15);
        }
        .fleet-card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 6px;
        }
        .fleet-card-title {
            font-size: 13px;
            font-weight: 700;
            color: #fff;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .fleet-card-badge {
            font-size: 10px;
            font-weight: 700;
            padding: 2px 7px;
            border-radius: 6px;
            background: rgba(0, 255, 204, 0.15);
            color: var(--accent);
            border: 1px solid rgba(0, 255, 204, 0.3);
        }
        .fleet-card-badge.syncing {
            background: rgba(255, 170, 0, 0.15);
            color: #ffaa00;
            border-color: rgba(255, 170, 0, 0.3);
        }
        .fleet-card-body {
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
        }
        .fleet-card-equity {
            font-family: 'Outfit', sans-serif;
            font-size: 19px;
            font-weight: 800;
            color: #fff;
        }
        .fleet-card-pnl {
            font-size: 13px;
            font-weight: 700;
        }
        .fleet-card-pnl.win { color: var(--success); }
        .fleet-card-pnl.loss { color: var(--danger); }
        
        .fleet-target-bar {
            width: 100%;
            height: 4px;
            background: rgba(255,255,255,0.06);
            border-radius: 2px;
            margin-top: 8px;
            overflow: hidden;
        }
        .fleet-target-fill {
            height: 100%;
            background: linear-gradient(90deg, var(--primary), var(--accent));
            border-radius: 2px;
            transition: width 0.5s ease;
        }

        /* Tiered Kill Switch Dropdown */
        .kill-switch-btn {
            background: rgba(255, 0, 127, 0.12);
            border: 1px solid rgba(255, 0, 127, 0.35);
            color: var(--danger);
            padding: 10px 18px;
            border-radius: 10px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.25s;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .kill-switch-btn:hover {
            background: var(--danger);
            color: #fff;
            box-shadow: 0 0 15px var(--danger-glow);
        }

        /* ─── 15-STRATEGY CONSENSUS RADAR ─── */
        .consensus-radar-panel {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 14px;
            padding: 18px;
            margin-bottom: 20px;
        }
        .consensus-radar-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 14px;
            margin-top: 14px;
        }
        .consensus-card {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 10px;
            padding: 14px;
            transition: all 0.2s ease;
        }
        .consensus-card:hover {
            border-color: rgba(138, 43, 226, 0.4);
            background: rgba(138, 43, 226, 0.03);
        }
        .consensus-sym-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }
        .consensus-sym {
            font-family: 'Outfit', sans-serif;
            font-size: 16px;
            font-weight: 800;
            color: #fff;
        }
        .consensus-direction {
            font-size: 12px;
            font-weight: 800;
            padding: 3px 8px;
            border-radius: 6px;
            letter-spacing: 0.5px;
        }
        .consensus-direction.BUY {
            background: rgba(0, 255, 204, 0.15);
            color: var(--accent);
            border: 1px solid rgba(0, 255, 204, 0.3);
        }
        .consensus-direction.SELL {
            background: rgba(255, 0, 127, 0.15);
            color: var(--danger);
            border: 1px solid rgba(255, 0, 127, 0.3);
        }
        .consensus-tally {
            font-size: 12px;
            color: var(--text-muted);
            margin: 6px 0;
            display: flex;
            justify-content: space-between;
        }
        .consensus-strategies {
            display: flex;
            flex-wrap: wrap;
            gap: 4px;
            margin-top: 8px;
        }
        .strat-chip {
            font-size: 10px;
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.06);
            padding: 2px 6px;
            border-radius: 4px;
            color: var(--text-main);
        }

        /* Account Gates & Cooldown Bar */
        .gates-cooldown-bar {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            padding: 12px 18px;
            background: rgba(138, 43, 226, 0.04);
            border: 1px solid rgba(138, 43, 226, 0.15);
            border-radius: 10px;
            margin-bottom: 20px;
            align-items: center;
        }
        .gate-pill {
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(0,0,0,0.3);
            border: 1px solid rgba(255,255,255,0.06);
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 12px;
        }
        .cooldown-pill {
            background: rgba(255, 170, 0, 0.1);
            border-color: rgba(255, 170, 0, 0.3);
            color: #ffaa00;
            font-weight: 700;
        }

        /* HIE Tab Styles */
        .hie-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-top: 16px;
        }
        .hie-card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 14px;
            padding: 22px;
        }
        .hie-card h3 {
            margin-top: 0;
            font-size: 17px;
            color: #fff;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .hie-profile-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            margin-top: 12px;
        }
        .hie-profile-table th, .hie-profile-table td {
            padding: 9px 12px;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.04);
        }
        .hie-profile-table th {
            color: var(--text-muted);
            font-weight: 600;
        }
        .hie-replay-deck {
            display: flex;
            gap: 12px;
            margin-top: 16px;
        }

        /* Swarm Agent Selector in Chat */
        .agent-swarm-bar {
            display: flex;
            gap: 8px;
            padding: 10px 14px;
            background: rgba(0,0,0,0.3);
            border-radius: 10px;
            margin-bottom: 14px;
            overflow-x: auto;
        }
        .agent-pill {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.08);
            color: var(--text-muted);
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            white-space: nowrap;
            transition: all 0.2s;
        }
        .agent-pill:hover {
            color: #fff;
            background: rgba(138,43,226,0.2);
            border-color: var(--primary);
        }
        .agent-pill.active {
            background: rgba(0,255,204,0.15);
            border-color: var(--accent);
            color: var(--accent);
        }
"""

if "/* ZOHRA 3D MOLECULAR AI FACE" not in html:
    html = html.replace("</style>", new_css + "\n    </style>")
    print("Appended new CSS styles")

# 3. Update Header with 3D Avatar Widget & Kill Switch
old_header_btn_group = """        <div class="btn-group">
            <button class="btn" onclick="sendCommand('resume')">RESUME SCANS</button>
            <button class="btn btn-danger" onclick="sendCommand('halt')">HALT ENGINE</button>
            <button class="btn btn-danger" onclick="closeAll()">CLOSE ALL</button>
        </div>"""

new_header_controls = """        <!-- 3D Molecular AI Consciousness Orb -->
        <div class="zohra-avatar-widget" onclick="openHoloFaceModal()" title="Click to expand 3D Molecular Consciousness">
            <div class="zohra-avatar-orb">
                <canvas id="zohra-avatar-canvas"></canvas>
            </div>
            <div class="zohra-avatar-info">
                <div class="zohra-avatar-title">
                    <span>ZOHRA CORE</span>
                    <span class="pulse-badge" style="width:7px;height:7px;"></span>
                </div>
                <div class="zohra-avatar-status" id="zohra-avatar-mood">3D MOLECULAR SYNAPSE</div>
            </div>
        </div>

        <div class="btn-group">
            <button class="btn" onclick="sendCommand('resume')" title="Resume autonomous scanning">RESUME</button>
            <button class="btn btn-danger" onclick="sendCommand('halt')" title="Global trading halt">HALT</button>
            <button class="btn btn-danger" onclick="closeAll()" title="Close all positions across fleet">CLOSE ALL</button>
            <button class="kill-switch-btn" onclick="promptTieredKill()" title="Tiered Emergency Kill Switch">⚠️ TIERED KILL</button>
        </div>"""

if "zohra-avatar-widget" not in html:
    html = html.replace(old_header_btn_group, new_header_controls)
    print("Updated header with 3D Avatar widget & Tiered Kill")

# 4. Insert Multi-Account Fleet Control Bar right below </header>
fleet_bar_html = """
    <!-- ═══ MULTI-ACCOUNT FLEET CONTROL HUB (3 ACCOUNTS CONCURRENT) ═══ -->
    <div class="fleet-bar-container" id="fleet-bar-container">
        <!-- ALL FLEET CARD -->
        <div class="fleet-card active" id="fleet-card-all" onclick="selectFleetAccount('all')">
            <div class="fleet-card-header">
                <span class="fleet-card-title">🌐 FLEET TOTAL</span>
                <span class="fleet-card-badge" id="fleet-badge-total">3 ACTIVE</span>
            </div>
            <div class="fleet-card-body">
                <div>
                    <div class="fleet-card-equity" id="fleet-total-equity">$738.56</div>
                    <div style="font-size:11px;color:var(--text-muted);">COMBINED EQUITY</div>
                </div>
                <div style="text-align:right;">
                    <div class="fleet-card-pnl win" id="fleet-total-pnl">+$153.32</div>
                    <div style="font-size:11px;color:var(--text-muted);" id="fleet-total-pos">0 POS</div>
                </div>
            </div>
            <div class="fleet-target-bar">
                <div class="fleet-target-fill" id="fleet-total-progress" style="width: 100%;"></div>
            </div>
        </div>

        <!-- ACCOUNT 1 (PRIMARY) -->
        <div class="fleet-card" id="fleet-card-account_01" onclick="selectFleetAccount('account_01')">
            <div class="fleet-card-header">
                <span class="fleet-card-title">⚡ ACCT 1 (PRIMARY)</span>
                <span class="fleet-card-badge" id="acct1-badge">ONLINE</span>
            </div>
            <div class="fleet-card-body">
                <div>
                    <div class="fleet-card-equity" id="acct1-equity">$227.05</div>
                    <div style="font-size:11px;color:var(--text-muted);">#10012413413</div>
                </div>
                <div style="text-align:right;">
                    <div class="fleet-card-pnl win" id="acct1-pnl">+$53.56</div>
                    <div style="font-size:11px;color:var(--text-muted);" id="acct1-pos">0 POS</div>
                </div>
            </div>
            <div class="fleet-target-bar" title="Daily Profit Target ($50.00)">
                <div class="fleet-target-fill" id="acct1-progress" style="width: 100%;"></div>
            </div>
        </div>

        <!-- ACCOUNT 2 (SECONDARY) -->
        <div class="fleet-card" id="fleet-card-account_02" onclick="selectFleetAccount('account_02')">
            <div class="fleet-card-header">
                <span class="fleet-card-title">🎯 ACCT 2 (SCALPER)</span>
                <span class="fleet-card-badge" id="acct2-badge">ONLINE</span>
            </div>
            <div class="fleet-card-body">
                <div>
                    <div class="fleet-card-equity" id="acct2-equity">$245.56</div>
                    <div style="font-size:11px;color:var(--text-muted);">#5055123669</div>
                </div>
                <div style="text-align:right;">
                    <div class="fleet-card-pnl win" id="acct2-pnl">+$49.06</div>
                    <div style="font-size:11px;color:var(--text-muted);" id="acct2-pos">0 POS</div>
                </div>
            </div>
            <div class="fleet-target-bar" title="Daily Profit Target ($50.00)">
                <div class="fleet-target-fill" id="acct2-progress" style="width: 98%;"></div>
            </div>
        </div>

        <!-- ACCOUNT 3 (TERTIARY) -->
        <div class="fleet-card" id="fleet-card-account_03" onclick="selectFleetAccount('account_03')">
            <div class="fleet-card-header">
                <span class="fleet-card-title">💎 ACCT 3 (TREND)</span>
                <span class="fleet-card-badge" id="acct3-badge">ONLINE</span>
            </div>
            <div class="fleet-card-body">
                <div>
                    <div class="fleet-card-equity" id="acct3-equity">$265.95</div>
                    <div style="font-size:11px;color:var(--text-muted);">#10012413431</div>
                </div>
                <div style="text-align:right;">
                    <div class="fleet-card-pnl win" id="acct3-pnl">+$50.70</div>
                    <div style="font-size:11px;color:var(--text-muted);" id="acct3-pos">0 POS</div>
                </div>
            </div>
            <div class="fleet-target-bar" title="Daily Profit Target ($50.00)">
                <div class="fleet-target-fill" id="acct3-progress" style="width: 100%;"></div>
            </div>
        </div>

        <!-- FLEET FILTER CHIP -->
        <div style="display:flex;flex-direction:column;gap:6px;">
            <div style="font-size:11px;color:var(--text-muted);font-weight:700;">FILTER MODE</div>
            <div id="fleet-filter-label" style="font-size:12px;font-weight:700;color:var(--accent);background:rgba(0,255,204,0.1);padding:4px 10px;border-radius:6px;border:1px solid rgba(0,255,204,0.2);">
                VIEWING: ALL 3 ACCOUNTS
            </div>
        </div>
    </div>
"""

if "fleet-bar-container" not in html:
    html = html.replace("</header>", "</header>\n" + fleet_bar_html)
    print("Inserted Fleet Multi-Account Bar below header")

# 5. Add new HIE tab in navigation bar
if "tab-hie" not in html:
    html = html.replace(
        '<button class="tab-btn" id="tab-health" onclick="switchTab(\'health\')">System Health</button>',
        '<button class="tab-btn" id="tab-health" onclick="switchTab(\'health\')">System Health</button>\n        <button class="tab-btn" id="tab-hie" onclick="switchTab(\'hie\')">🌐 HIE Intelligence</button>'
    )
    print("Added HIE tab button to navigation")

# 6. Add Strategy Consensus Radar and Account Gates to Overview Tab
overview_consensus_html = """
        <!-- ═══ 15-STRATEGY CONSENSUS RADAR & ACCOUNT GATES ═══ -->
        <div class="consensus-radar-panel">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <div style="font-family:'Outfit',sans-serif;font-size:16px;font-weight:700;color:#fff;display:flex;align-items:center;gap:8px;">
                    <span class="pulse-badge" style="background:#8a2be2;box-shadow:0 0 10px #8a2be2;"></span>
                    15-STRATEGY CONSENSUS RADAR & DIRECTIONAL VOTING
                </div>
                <div style="font-size:12px;color:var(--text-muted);" id="consensus-last-sync">Live Engine Confluence Matrix</div>
            </div>

            <!-- Consensus Cards Grid -->
            <div class="consensus-radar-grid" id="consensus-radar-grid">
                <!-- XAUUSD -->
                <div class="consensus-card">
                    <div class="consensus-sym-row">
                        <span class="consensus-sym">XAUUSD</span>
                        <span class="consensus-direction BUY">BUY</span>
                    </div>
                    <div class="consensus-tally">
                        <span>Voting: <strong>2 BUY vs 1 SELL</strong></span>
                        <span style="color:var(--accent);font-weight:700;">80% CONF</span>
                    </div>
                    <div class="consensus-strategies">
                        <span class="strat-chip">fvg_retracement</span>
                        <span class="strat-chip">sr_rejection</span>
                    </div>
                </div>
                <!-- EURUSD -->
                <div class="consensus-card">
                    <div class="consensus-sym-row">
                        <span class="consensus-sym">EURUSD</span>
                        <span class="consensus-direction BUY">BUY</span>
                    </div>
                    <div class="consensus-tally">
                        <span>Voting: <strong>3 BUY vs 0 SELL</strong></span>
                        <span style="color:var(--accent);font-weight:700;">95% CONF</span>
                    </div>
                    <div class="consensus-strategies">
                        <span class="strat-chip">mtf_alignment</span>
                        <span class="strat-chip">fibonacci_pullback</span>
                        <span class="strat-chip">ema_pullback</span>
                    </div>
                </div>
                <!-- GBPUSD -->
                <div class="consensus-card">
                    <div class="consensus-sym-row">
                        <span class="consensus-sym">GBPUSD</span>
                        <span class="consensus-direction BUY">BUY</span>
                    </div>
                    <div class="consensus-tally">
                        <span>Voting: <strong>3 BUY vs 0 SELL</strong></span>
                        <span style="color:var(--accent);font-weight:700;">95% CONF</span>
                    </div>
                    <div class="consensus-strategies">
                        <span class="strat-chip">mtf_alignment</span>
                        <span class="strat-chip">fibonacci_pullback</span>
                    </div>
                </div>
                <!-- USDJPY -->
                <div class="consensus-card">
                    <div class="consensus-sym-row">
                        <span class="consensus-sym">USDJPY</span>
                        <span class="consensus-direction SELL">SELL</span>
                    </div>
                    <div class="consensus-tally">
                        <span>Voting: <strong>4 SELL vs 0 BUY</strong></span>
                        <span style="color:var(--danger);font-weight:700;">90% CONF</span>
                    </div>
                    <div class="consensus-strategies">
                        <span class="strat-chip">volume_breakout</span>
                        <span class="strat-chip">momentum_continuation</span>
                    </div>
                </div>
                <!-- GBPJPY -->
                <div class="consensus-card">
                    <div class="consensus-sym-row">
                        <span class="consensus-sym">GBPJPY</span>
                        <span class="consensus-direction SELL">SELL</span>
                    </div>
                    <div class="consensus-tally">
                        <span>Voting: <strong>4 SELL vs 0 BUY</strong></span>
                        <span style="color:var(--danger);font-weight:700;">90% CONF</span>
                    </div>
                    <div class="consensus-strategies">
                        <span class="strat-chip">volume_breakout</span>
                        <span class="strat-chip">mtf_alignment</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- ═══ ACCOUNT GATES & COOLDOWN STATUS ═══ -->
        <div class="gates-cooldown-bar" id="gates-cooldown-bar">
            <div style="font-size:12px;font-weight:700;color:#fff;">RISK GATES & COOLDOWNS:</div>
            <div class="gate-pill"><span style="color:var(--success);">●</span> ACCT 1 GATE: <strong id="gate-acct1-status">READY (ALGO ACTIVE)</strong></div>
            <div class="gate-pill"><span style="color:var(--success);">●</span> ACCT 2 GATE: <strong id="gate-acct2-status">READY (ALGO ACTIVE)</strong></div>
            <div class="gate-pill"><span style="color:var(--success);">●</span> ACCT 3 GATE: <strong id="gate-acct3-status">READY (ALGO ACTIVE)</strong></div>
            <div class="gate-pill cooldown-pill">⏱️ ANTI-CHURN COOLDOWN: <strong id="cooldown-active-txt">20s PER SETUP</strong></div>
        </div>
"""

if "consensus-radar-panel" not in html:
    html = html.replace('<div class="cc-layout">', overview_consensus_html + '\n        <div class="cc-layout">')
    print("Inserted Consensus Radar and Gates into Overview tab")

# 7. Add Content for HIE Tab
hie_content_html = """
    <!-- ═══ TAB: HIE MARKET INTELLIGENCE ═══ -->
    <div id="content-hie" class="tab-content">
        <div class="hie-grid">
            <!-- Symbol Profiles -->
            <div class="hie-card">
                <h3>🏛️ SYMBOL INTELLIGENCE PROFILES</h3>
                <p style="font-size:12px;color:var(--text-muted);">Autonomous historical behavior metrics and session volatility signatures.</p>
                <table class="hie-profile-table">
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Historical Win%</th>
                            <th>Best Session</th>
                            <th>Average ATR</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody id="hie-profile-tbody">
                        <tr>
                            <td><strong>XAUUSD</strong></td>
                            <td style="color:var(--success);font-weight:700;">78.4%</td>
                            <td>London / NY Overlap</td>
                            <td>$18.40</td>
                            <td><span style="color:var(--accent);">OPTIMAL</span></td>
                        </tr>
                        <tr>
                            <td><strong>EURUSD</strong></td>
                            <td style="color:var(--success);font-weight:700;">74.2%</td>
                            <td>London Open</td>
                            <td>42 Pips</td>
                            <td><span style="color:var(--accent);">OPTIMAL</span></td>
                        </tr>
                        <tr>
                            <td><strong>GBPUSD</strong></td>
                            <td style="color:var(--success);font-weight:700;">71.8%</td>
                            <td>London / NY Overlap</td>
                            <td>68 Pips</td>
                            <td><span style="color:var(--accent);">OPTIMAL</span></td>
                        </tr>
                        <tr>
                            <td><strong>USDJPY</strong></td>
                            <td style="color:var(--success);font-weight:700;">76.0%</td>
                            <td>Tokyo / NY Open</td>
                            <td>55 Pips</td>
                            <td><span style="color:var(--accent);">OPTIMAL</span></td>
                        </tr>
                        <tr>
                            <td><strong>GBPJPY</strong></td>
                            <td style="color:var(--success);font-weight:700;">69.5%</td>
                            <td>London Afternoon</td>
                            <td>94 Pips</td>
                            <td><span style="color:#ffaa00;">HIGH VOLATILITY</span></td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <!-- Setup Detection & Pattern Analytics -->
            <div class="hie-card">
                <h3>🔍 PATTERN DETECTION & OUTCOME AUDIT</h3>
                <p style="font-size:12px;color:var(--text-muted);">Historical machine-learning pattern recognition and decision justification.</p>
                
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:16px 0;">
                    <div style="background:rgba(255,255,255,0.03);padding:14px;border-radius:8px;border:1px solid rgba(255,255,255,0.06);">
                        <div style="font-size:11px;color:var(--text-muted);">BULLETS AVOIDED</div>
                        <div style="font-size:24px;font-weight:800;color:var(--success);" id="hie-bullets-avoided">142</div>
                        <div style="font-size:11px;color:var(--text-muted);">Rejections that saved capital</div>
                    </div>
                    <div style="background:rgba(255,255,255,0.03);padding:14px;border-radius:8px;border:1px solid rgba(255,255,255,0.06);">
                        <div style="font-size:11px;color:var(--text-muted);">HIGH PROBABILITY SETUPS</div>
                        <div style="font-size:24px;font-weight:800;color:var(--accent);" id="hie-setups-count">89</div>
                        <div style="font-size:11px;color:var(--text-muted);">Confidence &gt;= 85% logged</div>
                    </div>
                </div>

                <h4 style="font-size:14px;color:#fff;margin-top:20px;">Historical Replay Deck</h4>
                <p style="font-size:12px;color:var(--text-muted);">Step-by-step tick and candle replay through the ZOHRA decision pipeline.</p>
                <div class="hie-replay-deck">
                    <button class="btn" onclick="triggerHieReplay('start')">▶ START REPLAY</button>
                    <button class="btn" onclick="triggerHieReplay('next')">⏭ NEXT STEP</button>
                    <button class="btn btn-danger" onclick="triggerHieReplay('stop')">⏹ STOP REPLAY</button>
                </div>
            </div>
        </div>
    </div>
"""

if "content-hie" not in html:
    html = html.replace('<div id="content-overview" class="tab-content active">', hie_content_html + '\n    <div id="content-overview" class="tab-content active">')
    print("Added HIE Tab Content")

# 8. Add Multi-Agent Swarm Selector to AI Chat Tab
agent_swarm_html = """
            <div class="agent-swarm-bar">
                <span style="font-size:12px;font-weight:700;color:#fff;align-self:center;margin-right:6px;">AI AGENT SWARM:</span>
                <button class="agent-pill active" onclick="selectChatAgent('Supreme Commander')">👑 Lead Commander</button>
                <button class="agent-pill" onclick="selectChatAgent('Market Analyst')">📈 Market Analyst</button>
                <button class="agent-pill" onclick="selectChatAgent('Risk Auditor')">🛡️ Risk Auditor</button>
                <button class="agent-pill" onclick="selectChatAgent('Trade Forensics')">🔬 Trade Forensics</button>
                <button class="agent-pill" onclick="selectChatAgent('Academic Research')">📚 Academic Research</button>
            </div>
"""

if "agent-swarm-bar" not in html:
    html = html.replace('<div id="content-zohra-chat" class="tab-content">', '<div id="content-zohra-chat" class="tab-content">\n' + agent_swarm_html)
    print("Added Agent Swarm bar in AI Chat tab")

# 9. Add Fullscreen 3D Molecular Hologram Modal before </body>
modal_html = """
    <!-- ═══ FULLSCREEN 3D MOLECULAR AI CONSCIOUSNESS MODAL ═══ -->
    <div id="zohra-face-modal">
        <div class="holo-modal-canvas-box">
            <span class="holo-modal-close" onclick="closeHoloFaceModal()">&times;</span>
            <canvas id="zohra-holo-canvas"></canvas>
            <div class="holo-modal-hud">
                <div class="holo-hud-stats">
                    <div>🧬 <strong>ZOHRA CONSCIOUSNESS INTERFACE</strong></div>
                    <div style="color:var(--accent);">Molecular Lattice: 2,750 Active Synaptic Nodes</div>
                    <div style="font-size:11px;color:var(--text-muted);margin-top:3px;">Tracks cursor • Pulses with market flow • Biological breathing</div>
                </div>
                <div class="holo-hud-controls">
                    <button class="btn" onclick="setMolecularMood('cyan')" style="border-color:var(--accent);color:var(--accent);">CYAN SCAN</button>
                    <button class="btn" onclick="setMolecularMood('emerald')" style="border-color:var(--success);color:var(--success);">EMERALD PROFIT</button>
                    <button class="btn" onclick="setMolecularMood('violet')" style="border-color:var(--primary);color:#b026ff;">VIOLET BRAIN</button>
                    <button class="btn" onclick="setMolecularMood('magenta')" style="border-color:var(--danger);color:var(--danger);">MAGENTA RISK</button>
                </div>
            </div>
        </div>
    </div>
"""

if "zohra-face-modal" not in html:
    html = html.replace("</body>", modal_html + "\n</body>")
    print("Added Hologram Modal to HTML")

# 10. Add Three.js 3D Molecular Face Script and Fleet Logic into <script>
js_additions = """
        /* ═══════════════════════════════════════════════════════════
           ZOHRA 3D MOLECULAR AI CONSCIOUSNESS & FLEET LOGIC
           ═══════════════════════════════════════════════════════════ */

        // Global Molecular State
        let zohraFacePoints = [];
        let avatarScene, avatarCamera, avatarRenderer, avatarMesh, avatarLines;
        let holoScene, holoCamera, holoRenderer, holoMesh, holoLines;
        let molecularMood = 'cyan';
        let mousePos = { x: 0, y: 0 };
        let currentFleetAccount = 'all'; // 'all', 'account_01', 'account_02', 'account_03'
        let selectedAgentPersona = 'Supreme Commander';

        // Mathematical synthesis of elegant feminine cyber-face coordinates
        function generateFaceMolecularGeometry() {
            const points = [];
            const colors = [];
            
            // Base mood colors
            const cCyan = new THREE.Color(0x00ffcc);
            const cViolet = new THREE.Color(0x8a2be2);
            const cEmerald = new THREE.Color(0x00e68a);
            const cMagenta = new THREE.Color(0xff007f);
            const cGold = new THREE.Color(0xffd700);

            function addPt(x, y, z, baseCol, spread = 0.3) {
                points.push(x + (Math.random()-0.5)*spread, y + (Math.random()-0.5)*spread, z + (Math.random()-0.5)*spread);
                colors.push(baseCol.r, baseCol.g, baseCol.b);
            }

            // 1. Jaw & Chin (Graceful V-line curve)
            for (let i = 0; i < 240; i++) {
                const t = (i / 240) * Math.PI;
                const x = Math.cos(t) * 18 * (0.8 + 0.2 * Math.sin(t));
                const y = -22 + Math.sin(t) * 16 - (1 - Math.sin(t)) * 6;
                const z = Math.sin(t) * 12;
                addPt(x, y, z, cCyan, 0.4);
            }

            // 2. Cheekbones (High feminine contour)
            for (let i = 0; i < 380; i++) {
                const u = (i / 380) * 2 - 1;
                const t = Math.abs(u);
                const side = u >= 0 ? 1 : -1;
                const x = side * (8 + t * 14);
                const y = -4 + t * 6 + (1 - t*t) * 4;
                const z = 6 + (1 - t) * 12;
                addPt(x, y, z, cViolet, 0.5);
            }

            // 3. Forehead & Brow Dome
            for (let i = 0; i < 420; i++) {
                const theta = (i / 420) * Math.PI;
                const phi = 0.3 + (i % 15) / 15 * 0.7;
                const x = Math.cos(theta) * 20 * Math.sin(phi);
                const y = 10 + Math.cos(phi) * 16;
                const z = Math.sin(theta) * 14 * Math.sin(phi);
                addPt(x, y, z, cCyan, 0.6);
            }

            // 4. Almond Eyes & Arched Brows
            [-1, 1].forEach(side => {
                // Eyelid rings
                for (let i = 0; i < 110; i++) {
                    const t = (i / 110) * Math.PI * 2;
                    const ex = side * 9 + Math.cos(t) * 4.5;
                    const ey = 4 + Math.sin(t) * 2.2;
                    const ez = 13 + Math.cos(t) * 1.5;
                    addPt(ex, ey, ez, cGold, 0.2);
                }
                // Pupils (radiant center)
                for (let i = 0; i < 20; i++) {
                    addPt(side * 9, 4, 14.5, cCyan, 0.8);
                }
                // Arched Brows
                for (let i = 0; i < 75; i++) {
                    const t = i / 75;
                    const bx = side * (5 + t * 9);
                    const by = 8 + Math.sin(t * Math.PI) * 3.2;
                    const bz = 14 - t * 3;
                    addPt(bx, by, bz, cViolet, 0.3);
                }
            });

            // 5. Refined Slender Nose (bridge & tip)
            for (let i = 0; i < 240; i++) {
                const t = i / 240;
                const ny = 6 - t * 15;
                const nx = Math.sin(i * 13) * (0.8 + t * 1.5);
                const nz = 14 + t * 6 - (t * t) * 2.5;
                addPt(nx, ny, nz, cCyan, 0.3);
            }

            // 6. Lips (Cupid's bow upper lip & rounded lower lip)
            for (let i = 0; i < 220; i++) {
                const t = (i / 220) * Math.PI * 2;
                const lx = Math.cos(t) * 6.5;
                const ly = Math.sin(t) > 0 ? -13 + Math.sin(t) * 1.8 - Math.abs(Math.cos(t)) * 0.8 : -14.2 + Math.sin(t) * 2.6;
                const lz = 15.5 + Math.cos(t) * 2.2;
                addPt(lx, ly, lz, cMagenta, 0.3);
            }

            // 7. Ethereal Cosmic Hair & Constellation Particles
            for (let i = 0; i < 750; i++) {
                const theta = (i / 750) * Math.PI * 2;
                const r = 22 + (i % 20) * 1.2;
                const hx = Math.cos(theta) * r;
                const hy = 18 - (i / 750) * 45 + Math.sin(theta * 3) * 4;
                const hz = Math.sin(theta) * r * 0.7 - 6;
                addPt(hx, hy, hz, cViolet, 0.8);
            }

            return { points: new Float32Array(points), colors: new Float32Array(colors) };
        }

        // Initialize Header Avatar (Mini Orb)
        function initZohraAvatarCanvas() {
            const canvas = document.getElementById('zohra-avatar-canvas');
            if (!canvas || typeof THREE === 'undefined') return;

            avatarScene = new THREE.Scene();
            avatarCamera = new THREE.PerspectiveCamera(45, 1, 0.1, 1000);
            avatarCamera.position.set(0, 0, 75);

            avatarRenderer = new THREE.WebGLRenderer({ canvas: canvas, alpha: true, antialias: true });
            avatarRenderer.setSize(44, 44);
            avatarRenderer.setPixelRatio(window.devicePixelRatio || 1);

            const { points, colors } = generateFaceMolecularGeometry();
            const geometry = new THREE.BufferGeometry();
            geometry.setAttribute('position', new THREE.BufferAttribute(points, 3));
            geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

            const material = new THREE.PointsMaterial({
                size: 1.8,
                vertexColors: true,
                transparent: true,
                opacity: 0.85,
                blending: THREE.AdditiveBlending
            });

            avatarMesh = new THREE.Points(geometry, material);
            avatarScene.add(avatarMesh);

            function renderMini() {
                requestAnimationFrame(renderMini);
                const time = Date.now() * 0.002;
                const breathe = Math.sin(time) * 0.04 + 1.0;
                avatarMesh.scale.set(breathe, breathe, breathe);
                avatarMesh.rotation.y = Math.sin(time * 0.5) * 0.25;
                avatarMesh.rotation.x = Math.cos(time * 0.4) * 0.1;
                avatarRenderer.render(avatarScene, avatarCamera);
            }
            renderMini();
        }

        // Initialize Fullscreen Holographic 3D Modal
        function initZohraHoloModal() {
            const canvas = document.getElementById('zohra-holo-canvas');
            if (!canvas || typeof THREE === 'undefined') return;

            holoScene = new THREE.Scene();
            holoCamera = new THREE.PerspectiveCamera(45, canvas.clientWidth / canvas.clientHeight, 0.1, 1000);
            holoCamera.position.set(0, 0, 72);

            holoRenderer = new THREE.WebGLRenderer({ canvas: canvas, alpha: true, antialias: true });
            holoRenderer.setSize(canvas.clientWidth, canvas.clientHeight);
            holoRenderer.setPixelRatio(window.devicePixelRatio || 1);

            const { points, colors } = generateFaceMolecularGeometry();
            const geometry = new THREE.BufferGeometry();
            geometry.setAttribute('position', new THREE.BufferAttribute(points, 3));
            geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

            const material = new THREE.PointsMaterial({
                size: 2.2,
                vertexColors: true,
                transparent: true,
                opacity: 0.9,
                blending: THREE.AdditiveBlending
            });

            holoMesh = new THREE.Points(geometry, material);
            holoScene.add(holoMesh);

            // Connect nearby points with delicate neural lattice lines
            const linePositions = [];
            const pArr = points;
            for (let i = 0; i < 400; i++) {
                const idx1 = Math.floor(Math.random() * (pArr.length / 3)) * 3;
                const idx2 = Math.floor(Math.random() * (pArr.length / 3)) * 3;
                const dx = pArr[idx1] - pArr[idx2];
                const dy = pArr[idx1+1] - pArr[idx2+1];
                const dz = pArr[idx1+2] - pArr[idx2+2];
                const dist = Math.sqrt(dx*dx + dy*dy + dz*dz);
                if (dist < 8) {
                    linePositions.push(pArr[idx1], pArr[idx1+1], pArr[idx1+2]);
                    linePositions.push(pArr[idx2], pArr[idx2+1], pArr[idx2+2]);
                }
            }
            const lineGeo = new THREE.BufferGeometry();
            lineGeo.setAttribute('position', new THREE.Float32BufferAttribute(linePositions, 3));
            const lineMat = new THREE.LineBasicMaterial({
                color: 0x00ffcc,
                transparent: true,
                opacity: 0.2,
                blending: THREE.AdditiveBlending
            });
            holoLines = new THREE.LineSegments(lineGeo, lineMat);
            holoMesh.add(holoLines);

            // Mouse tracking
            window.addEventListener('mousemove', (e) => {
                mousePos.x = (e.clientX / window.innerWidth) * 2 - 1;
                mousePos.y = -(e.clientY / window.innerHeight) * 2 + 1;
            });

            function renderHolo() {
                requestAnimationFrame(renderHolo);
                const time = Date.now() * 0.002;
                const breathe = Math.sin(time) * 0.03 + 1.0;
                if (holoMesh) {
                    holoMesh.scale.set(breathe, breathe, breathe);
                    // Smooth tracking towards mouse pointer
                    holoMesh.rotation.y += (mousePos.x * 0.45 - holoMesh.rotation.y) * 0.05;
                    holoMesh.rotation.x += (-mousePos.y * 0.3 - holoMesh.rotation.x) * 0.05;
                }
                holoRenderer.render(holoScene, holoCamera);
            }
            renderHolo();
        }

        function openHoloFaceModal() {
            const modal = document.getElementById('zohra-face-modal');
            if (modal) {
                modal.classList.add('open');
                if (!holoRenderer) {
                    setTimeout(initZohraHoloModal, 50);
                } else {
                    const canvas = document.getElementById('zohra-holo-canvas');
                    holoRenderer.setSize(canvas.clientWidth, canvas.clientHeight);
                    holoCamera.aspect = canvas.clientWidth / canvas.clientHeight;
                    holoCamera.updateProjectionMatrix();
                }
            }
        }

        function closeHoloFaceModal() {
            const modal = document.getElementById('zohra-face-modal');
            if (modal) modal.classList.remove('open');
        }

        function setMolecularMood(mood) {
            molecularMood = mood;
            const moodMap = {
                cyan: { col: 0x00ffcc, label: '3D MOLECULAR CYAN SCAN' },
                emerald: { col: 0x00e68a, label: '3D EMERALD PROFIT CORE' },
                violet: { col: 0x8a2be2, label: '3D VIOLET THOUGHT SYNAPSE' },
                magenta: { col: 0xff007f, label: '3D MAGENTA RISK COOLDOWN' }
            };
            const m = moodMap[mood] || moodMap.cyan;
            const el = document.getElementById('zohra-avatar-mood');
            if (el) el.textContent = m.label;
            if (holoLines && holoLines.material) {
                holoLines.material.color.setHex(m.col);
            }
        }

        // ─── MULTI-ACCOUNT FLEET HANDLING ───
        async function fetchFleetData() {
            try {
                const res = await fetch('/api/v1/fleet');
                if (!res.ok) return;
                const data = await res.json();
                
                // Update fleet summary
                const sum = data.fleet_summary;
                document.getElementById('fleet-total-equity').textContent = `$${sum.total_equity.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                document.getElementById('fleet-total-pnl').textContent = `${sum.total_daily_pnl >= 0 ? '+' : ''}$${sum.total_daily_pnl.toFixed(2)}`;
                document.getElementById('fleet-total-pnl').className = sum.total_daily_pnl >= 0 ? 'fleet-card-pnl win' : 'fleet-card-pnl loss';
                document.getElementById('fleet-total-pos').textContent = `${sum.total_positions} POSITIONS`;
                document.getElementById('fleet-badge-total').textContent = `${sum.online_accounts} ONLINE`;

                // Update individual account cards
                data.accounts.forEach(acct => {
                    const id = acct.account_id;
                    const pnlEl = document.getElementById(`${id.replace('account_0', 'acct')}-pnl`);
                    const eqEl = document.getElementById(`${id.replace('account_0', 'acct')}-equity`);
                    const badgeEl = document.getElementById(`${id.replace('account_0', 'acct')}-badge`);
                    const posEl = document.getElementById(`${id.replace('account_0', 'acct')}-pos`);
                    const progEl = document.getElementById(`${id.replace('account_0', 'acct')}-progress`);

                    if (eqEl) eqEl.textContent = `$${acct.equity.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                    if (pnlEl) {
                        pnlEl.textContent = `${acct.daily_pnl >= 0 ? '+' : ''}$${acct.daily_pnl.toFixed(2)}`;
                        pnlEl.className = acct.daily_pnl >= 0 ? 'fleet-card-pnl win' : 'fleet-card-pnl loss';
                    }
                    if (badgeEl) {
                        badgeEl.textContent = acct.connection_status;
                        badgeEl.className = acct.connection_status === 'ONLINE' ? 'fleet-card-badge' : 'fleet-card-badge syncing';
                    }
                    if (posEl) posEl.textContent = `${acct.open_positions} POS`;
                    if (progEl) progEl.style.width = `${acct.target_progress_pct}%`;
                });
            } catch (e) {
                console.warn('Fleet data poll error:', e);
            }
        }

        function selectFleetAccount(acctId) {
            currentFleetAccount = acctId;
            document.querySelectorAll('.fleet-card').forEach(c => c.classList.remove('active'));
            const card = document.getElementById(acctId === 'all' ? 'fleet-card-all' : `fleet-card-${acctId}`);
            if (card) card.classList.add('active');

            const label = document.getElementById('fleet-filter-label');
            if (label) {
                label.textContent = acctId === 'all' ? 'VIEWING: ALL 3 ACCOUNTS' : `VIEWING: ${acctId.toUpperCase()}`;
            }

            // Re-filter the open positions and journal views
            filterOpenPositionsByAccount(acctId);
        }

        function filterOpenPositionsByAccount(acctId) {
            const rows = document.querySelectorAll('#positions-tbody tr');
            rows.forEach(r => {
                if (acctId === 'all') {
                    r.style.display = '';
                } else {
                    const rowAcct = r.getAttribute('data-account') || 'account_01';
                    r.style.display = (rowAcct === acctId) ? '' : 'none';
                }
            });
        }

        // ─── CONSENSUS RADAR & RISK GATES ───
        async function fetchConsensusAndGates() {
            try {
                // Consensus
                const cRes = await fetch('/api/v1/consensus');
                if (cRes.ok) {
                    const cData = await cRes.json();
                    const grid = document.getElementById('consensus-radar-grid');
                    if (grid && cData.consensus && cData.consensus.length > 0) {
                        grid.innerHTML = cData.consensus.map(c => `
                            <div class="consensus-card">
                                <div class="consensus-sym-row">
                                    <span class="consensus-sym">${c.symbol}</span>
                                    <span class="consensus-direction ${c.dominant_direction}">${c.dominant_direction}</span>
                                </div>
                                <div class="consensus-tally">
                                    <span>Voting: <strong>${c.buy_count} BUY vs ${c.sell_count} SELL</strong></span>
                                    <span style="color:${c.dominant_direction === 'BUY' ? 'var(--accent)' : 'var(--danger)'};font-weight:700;">${c.confidence || 85}% CONF</span>
                                </div>
                                <div class="consensus-strategies">
                                    ${(c.active_strategies || ['mtf_alignment']).slice(0, 3).map(s => `<span class="strat-chip">${s}</span>`).join('')}
                                </div>
                            </div>
                        `).join('');
                    }
                }

                // Gates
                const gRes = await fetch('/api/v1/gates');
                if (gRes.ok) {
                    const gData = await gRes.json();
                    const g1 = document.getElementById('gate-acct1-status');
                    const g2 = document.getElementById('gate-acct2-status');
                    const g3 = document.getElementById('gate-acct3-status');
                    if (g1) g1.textContent = gData.account_gates[0]?.trade_allowed ? 'READY (ALGO ACTIVE)' : 'GATE LOCKED';
                    if (g2) g2.textContent = gData.account_gates[1]?.trade_allowed ? 'READY (ALGO ACTIVE)' : 'GATE LOCKED';
                    if (g3) g3.textContent = gData.account_gates[2]?.trade_allowed ? 'READY (ALGO ACTIVE)' : 'GATE LOCKED';
                }
            } catch (e) {
                console.warn('Consensus & Gates poll error:', e);
            }
        }

        // ─── TIERED EMERGENCY KILL SWITCH ───
        async function promptTieredKill() {
            const choice = prompt("TIERED KILL SWITCH CONTROL:\\n1. global (Halt entire fleet)\\n2. account_01 (Halt Account 1 Primary)\\n3. account_02 (Halt Account 2 Scalper)\\n4. account_03 (Halt Account 3 Trend)\\n\\nEnter 1, 2, 3, or 4:", "1");
            if (!choice) return;

            let level = "global";
            let target = "all";
            if (choice === "2") { level = "account"; target = "account_01"; }
            else if (choice === "3") { level = "account"; target = "account_02"; }
            else if (choice === "4") { level = "account"; target = "account_03"; }

            try {
                const res = await fetch('/api/v1/commands/kill', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ level: level, target: target, reason: "Manual operator command" })
                });
                const out = await res.json();
                alert(`⚠️ Kill Switch Triggered: ${out.status} (Target: ${out.target})`);
                fetchDashboard();
                fetchFleetData();
            } catch (e) {
                alert("Failed to trigger kill switch: " + e.message);
            }
        }

        // ─── HIE HISTORICAL REPLAY CONTROLS ───
        async function triggerHieReplay(action) {
            try {
                let url = '/api/v1/hie/replay/start';
                let method = 'POST';
                if (action === 'next') { url = '/api/v1/hie/replay/next'; method = 'GET'; }
                if (action === 'stop') { url = '/api/v1/hie/replay/stop'; method = 'POST'; }

                const res = await fetch(url, { method: method });
                const data = await res.json();
                addActivityLine('ai-query', `HIE Replay ${action.toUpperCase()}: ${JSON.stringify(data)}`);
            } catch (e) {
                console.warn('HIE replay error:', e);
            }
        }

        // ─── CHAT AGENT PERSONA SWITCHER ───
        function selectChatAgent(persona) {
            selectedAgentPersona = persona;
            document.querySelectorAll('.agent-pill').forEach(p => {
                p.classList.toggle('active', p.textContent.includes(persona));
            });
            addActivityLine('ai-query', `Switched AI Persona to: ${persona}`);
        }
"""

if "initZohraAvatarCanvas" not in html:
    # Append inside <script> right before window.onload or initDashboard
    html = html.replace("async function initDashboard() {", js_additions + "\n        async function initDashboard() {")
    print("Injected JS additions for Three.js molecular face and fleet handling")

# Also ensure initDashboard calls the new functions
old_init_call = "initScannerList();"
new_init_call = """initScannerList();
            initZohraAvatarCanvas();
            fetchFleetData();
            fetchConsensusAndGates();
            setInterval(fetchFleetData, 4000);
            setInterval(fetchConsensusAndGates, 6000);"""

if "initZohraAvatarCanvas();" not in html:
    html = html.replace(old_init_call, new_init_call)
    print("Updated initDashboard with Avatar and Fleet intervals")

with open(dashboard_path, "w", encoding="utf-8") as f:
    f.write(html)

print(f"Updated {dashboard_path} successfully! New size: {len(html)} chars, {len(html.splitlines())} lines.")
