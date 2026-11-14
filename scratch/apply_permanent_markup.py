import sys
sys.stdout.reconfigure(encoding='utf-8')

dashboard_path = "zohra/api/dashboard.html"
with open(dashboard_path, "r", encoding="utf-8") as f:
    text = f.read()

# 1. Replace static <header> content
old_header = """    <header>
        <div class="logo-container">
            <div class="pulse-badge"></div>
            <h1>ZOHRA | Institutional command center</h1>
        </div>
        <div class="btn-group">
            <button class="btn" onclick="sendCommand('resume')">RESUME SCANS</button>
            <button class="btn btn-danger" onclick="sendCommand('halt')">HALT ENGINE</button>
            <button class="btn btn-danger" onclick="closeAll()">CLOSE ALL</button>
        </div>
    </header>"""

new_header = """    <header>
        <div class="logo-container">
            <div class="pulse-badge"></div>
            <h1>ZOHRA | Institutional command center</h1>
        </div>

        <!-- 3D Molecular AI Consciousness Orb -->
        <div class="zohra-avatar-widget" onclick="openHoloFaceModal()" title="Click to expand 3D Molecular Consciousness">
            <div class="zohra-avatar-orb">
                <canvas id="zohra-avatar-canvas" width="44" height="44"></canvas>
            </div>
            <div class="zohra-avatar-info">
                <div class="zohra-avatar-title">
                    <span>ZOHRA CORE</span>
                    <span class="pulse-badge" style="width:7px;height:7px;"></span>
                </div>
                <div class="zohra-avatar-status" id="zohra-avatar-mood">3D MOLECULAR CYAN SCAN</div>
            </div>
        </div>

        <div class="btn-group">
            <button class="btn" onclick="sendCommand('resume')" title="Resume autonomous scanning">RESUME</button>
            <button class="btn btn-danger" onclick="sendCommand('halt')" title="Global trading halt">HALT</button>
            <button class="btn btn-danger" onclick="closeAll()" title="Close all positions across fleet">CLOSE ALL</button>
            <button class="kill-switch-btn" onclick="promptTieredKill()" title="Tiered Emergency Kill Switch">⚠️ TIERED KILL</button>
        </div>
    </header>

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
    </div>"""

if "zohra-avatar-widget" not in text:
    text = text.replace(old_header, new_header)
    print("Permanently replaced header and added fleet bar in HTML markup")

# 2. Add Consensus Radar & Gates into Overview tab
overview_marker = '<div id="content-overview" class="tab-content active">'
if "consensus-radar-panel" not in text:
    consensus_block = overview_marker + """
        <!-- ═══ 15-STRATEGY CONSENSUS RADAR & ACCOUNT GATES ═══ -->
        <div class="consensus-radar-panel" id="consensus-radar-panel">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <div style="font-family:'Outfit',sans-serif;font-size:16px;font-weight:700;color:#fff;display:flex;align-items:center;gap:8px;">
                    <span class="pulse-badge" style="background:#8a2be2;box-shadow:0 0 10px #8a2be2;"></span>
                    15-STRATEGY CONSENSUS RADAR & DIRECTIONAL VOTING
                </div>
                <div style="font-size:12px;color:var(--text-muted);" id="consensus-last-sync">Live Engine Confluence Matrix</div>
            </div>

            <div class="consensus-radar-grid" id="consensus-radar-grid">
                <div class="consensus-card">
                    <div class="consensus-sym-row"><span class="consensus-sym">XAUUSD</span><span class="consensus-direction BUY">BUY</span></div>
                    <div class="consensus-tally"><span>Voting: <strong>2 BUY vs 1 SELL</strong></span><span style="color:var(--accent);font-weight:700;">85% CONF</span></div>
                    <div class="consensus-strategies"><span class="strat-chip">fvg_retracement</span><span class="strat-chip">sr_rejection</span></div>
                </div>
                <div class="consensus-card">
                    <div class="consensus-sym-row"><span class="consensus-sym">EURUSD</span><span class="consensus-direction BUY">BUY</span></div>
                    <div class="consensus-tally"><span>Voting: <strong>3 BUY vs 0 SELL</strong></span><span style="color:var(--accent);font-weight:700;">95% CONF</span></div>
                    <div class="consensus-strategies"><span class="strat-chip">mtf_alignment</span><span class="strat-chip">fibonacci_pullback</span></div>
                </div>
                <div class="consensus-card">
                    <div class="consensus-sym-row"><span class="consensus-sym">GBPUSD</span><span class="consensus-direction BUY">BUY</span></div>
                    <div class="consensus-tally"><span>Voting: <strong>3 BUY vs 0 SELL</strong></span><span style="color:var(--accent);font-weight:700;">95% CONF</span></div>
                    <div class="consensus-strategies"><span class="strat-chip">mtf_alignment</span><span class="strat-chip">fibonacci_pullback</span></div>
                </div>
                <div class="consensus-card">
                    <div class="consensus-sym-row"><span class="consensus-sym">USDJPY</span><span class="consensus-direction SELL">SELL</span></div>
                    <div class="consensus-tally"><span>Voting: <strong>4 SELL vs 0 BUY</strong></span><span style="color:var(--danger);font-weight:700;">90% CONF</span></div>
                    <div class="consensus-strategies"><span class="strat-chip">volume_breakout</span><span class="strat-chip">momentum_continuation</span></div>
                </div>
                <div class="consensus-card">
                    <div class="consensus-sym-row"><span class="consensus-sym">GBPJPY</span><span class="consensus-direction SELL">SELL</span></div>
                    <div class="consensus-tally"><span>Voting: <strong>4 SELL vs 0 BUY</strong></span><span style="color:var(--danger);font-weight:700;">90% CONF</span></div>
                    <div class="consensus-strategies"><span class="strat-chip">volume_breakout</span><span class="strat-chip">mtf_alignment</span></div>
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
        </div>"""
    text = text.replace(overview_marker, consensus_block)
    print("Permanently added Consensus Radar & Gates to Overview markup")

# 3. Add 3D Face Modal before </body>
if "zohra-face-modal" not in text:
    modal_html = """    <!-- ═══ FULLSCREEN 3D MOLECULAR AI CONSCIOUSNESS MODAL ═══ -->
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
</body>"""
    text = text.replace("</body>", modal_html)
    print("Permanently added 3D Face Modal markup")

with open(dashboard_path, "w", encoding="utf-8") as f:
    f.write(text)

print("Saved permanent markup updates to dashboard.html!")
