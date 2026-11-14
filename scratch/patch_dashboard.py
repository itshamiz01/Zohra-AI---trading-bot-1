import os

dashboard_path = "zohra/api/dashboard.html"

with open(dashboard_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Replace loadPlaybackSimulation function
old_replay_func = """        function loadPlaybackSimulation(trade) {
            // Draw simulated candle charts step-by-step
            const container = document.getElementById('playback-chart-container');
            container.innerHTML = `<div id="playback-inner-chart" style="width: 100%; height: 100%;"></div>`;
            
            const options = {
                series: [{
                    data: [
                        { x: new Date(1538778600000), y: [6629.81, 6650.5, 6622.98, 6632.01] },
                        { x: new Date(1538780400000), y: [6632.01, 6643.59, 6620, 6630.11] },
                        { x: new Date(1538782200000), y: [6630.11, 6636.39, 6610, 6618.31] },
                        { x: new Date(1538784000000), y: [6618.31, 6625, 6590, 6608.23] },
                        { x: new Date(1538785800000), y: [6608.23, 6612, 6601.31, 6605.0] }
                    ]
                }],
                chart: {
                    type: 'candlestick',
                    height: 330,
                    background: 'transparent',
                    foreColor: '#838fa7',
                    toolbar: { show: false }
                },
                xaxis: {
                    type: 'datetime'
                },
                yaxis: {
                    tooltip: {
                        enabled: true
                    }
                }
            };
            const pChart = new ApexCharts(document.querySelector("#playback-inner-chart"), options);
            pChart.render();
            
            // Build decision timeline
            const tList = document.getElementById('timeline-log-list');
            tList.innerHTML = `
                <div class="timeline-step">
                    <strong>[${trade.timestamp_open.substring(11,19)}] Signal Scanned</strong>
                    <p style="font-size: 12px; color: var(--text-muted); margin: 4px 0;">Strategy ${trade.strategy_used} triggered alignment matrix.</p>
                </div>
                <div class="timeline-step">
                    <strong>Score Compiled: ${trade.confidence_score} Points</strong>
                    <p style="font-size: 12px; color: var(--text-muted); margin: 4px 0;">Structure: ${trade.score_structure} | SMC: ${trade.score_smc} | Volatility: ${trade.score_volatility}</p>
                </div>
                <div class="timeline-step">
                    <strong>Risk Approval Passed</strong>
                    <p style="font-size: 12px; color: var(--text-muted); margin: 4px 0;">Margin validation cleared at leverage 1:500.</p>
                </div>
                <div class="timeline-step closed">
                    <strong>Closed at exit price: ${trade.exit_price || 'N/A'}</strong>
                    <p style="font-size: 12px; color: var(--text-muted); margin: 4px 0;">Outcome: ${trade.pnl_usd >= 0 ? 'WIN' : 'LOSS'} | Exit code: ${trade.exit_reason_code || 'SL_HIT'}</p>
                </div>
            `;
            
            switchTab('playback');
        }"""

new_replay_func = """        async function loadPlaybackSimulation(trade) {
            const container = document.getElementById('playback-chart-container');
            container.innerHTML = `<div style="color: var(--text-muted); text-align: center; padding: 20px;">Fetching candle replay and decision data...</div>`;
            
            const ticket = trade.mt5_ticket || trade.trade_id;
            try {
                const res = await fetch(`/api/v1/advanced/replay?ticket=${ticket}`);
                const data = await res.json();
                
                if (data.success && data.candles && data.candles.length > 0) {
                    container.innerHTML = `<div id="playback-inner-chart" style="width: 100%; height: 100%;"></div>`;
                    
                    const options = {
                        series: [{
                            data: data.candles
                        }],
                        chart: {
                            type: 'candlestick',
                            height: 330,
                            background: 'transparent',
                            foreColor: '#838fa7',
                            toolbar: { show: false }
                        },
                        xaxis: {
                            type: 'datetime'
                        },
                        yaxis: {
                            tooltip: {
                                enabled: true
                            }
                        }
                    };
                    const pChart = new ApexCharts(document.querySelector("#playback-inner-chart"), options);
                    pChart.render();
                    
                    // Populate timeline
                    const tList = document.getElementById('timeline-log-list');
                    tList.innerHTML = data.timeline.map(step => `
                        <div class="timeline-step ${step.title.includes('Closed') ? 'closed' : ''}">
                            <strong>[${step.time}] ${step.title}</strong>
                            <p style="font-size: 12px; color: var(--text-muted); margin: 4px 0;">${step.text}</p>
                        </div>
                    `).join('');
                } else {
                    throw new Error("No replay data returned.");
                }
            } catch (e) {
                console.error("Replay fetch failed, using fallback:", e);
                container.innerHTML = `<div id="playback-inner-chart" style="width: 100%; height: 100%;"></div>`;
                const entry = parseFloat(trade.entry_price || 2000.0);
                const exit_p = parseFloat(trade.exit_price || entry);
                const mockCandles = Array.from({length: 15}, (_, idx) => {
                    const progress = idx / 14.0;
                    const c = entry + progress * (exit_p - entry);
                    const o = idx === 0 ? entry : (entry + (idx - 1) / 14.0 * (exit_p - entry));
                    return {
                        x: Date.now() - (15 - idx) * 15 * 60 * 1000,
                        y: [o, Math.max(o, c) + 0.5, Math.min(o, c) - 0.5, c]
                    };
                });
                
                const options = {
                    series: [{ data: mockCandles }],
                    chart: { type: 'candlestick', height: 330, background: 'transparent', foreColor: '#838fa7', toolbar: { show: false } },
                    xaxis: { type: 'datetime' },
                    yaxis: { tooltip: { enabled: true } }
                };
                const pChart = new ApexCharts(document.querySelector("#playback-inner-chart"), options);
                pChart.render();
                
                const tList = document.getElementById('timeline-log-list');
                tList.innerHTML = `
                    <div class="timeline-step">
                        <strong>[${trade.timestamp_open ? trade.timestamp_open.substring(11,19) : ''}] Signal Scanned</strong>
                        <p style="font-size: 12px; color: var(--text-muted); margin: 4px 0;">Strategy ${trade.strategy_used || 'scalp_m5'} triggered confluence matrix (Offline Fallback).</p>
                    </div>
                    <div class="timeline-step">
                        <strong>Score Compiled: ${trade.confidence_score} Points</strong>
                        <p style="font-size: 12px; color: var(--text-muted); margin: 4px 0;">Structure: ${trade.score_structure || 70} | SMC: ${trade.score_smc || 70} | Liquidity: ${trade.score_liquidity || 70}</p>
                    </div>
                    <div class="timeline-step closed">
                        <strong>Closed at exit price: ${trade.exit_price || 'N/A'}</strong>
                        <p style="font-size: 12px; color: var(--text-muted); margin: 4px 0;">Outcome: ${trade.pnl_usd >= 0 ? 'WIN' : 'LOSS'} | Exit code: ${trade.exit_reason_code || 'SL_HIT'}</p>
                    </div>
                `;
            }
            
            switchTab('playback');
        }"""

# Try direct replacement
content_norm = content.replace("\r\n", "\n")
old_replay_func_norm = old_replay_func.replace("\r\n", "\n")
new_replay_func_norm = new_replay_func.replace("\r\n", "\n")

if old_replay_func_norm in content_norm:
    content = content_norm.replace(old_replay_func_norm, new_replay_func_norm)
    print("SUCCESS: Replaced loadPlaybackSimulation function.")
else:
    print("WARNING: Could not find exact replay function.")

# 2. Inject backtest tab cards under simulators
risk_sim_card_end = """                        </div>
                    </div>
                </div>
            </div>"""

new_backtest_cards = """                        </div>
                    </div>
                </div>
            </div>

            <!-- Institutional Backtesting Lab Form -->
            <div class="card col-4">
                <h2>Historical Backtesting Lab</h2>
                <div style="display: flex; flex-direction: column; gap: 15px; margin-top: 10px;">
                    <div>
                        <label style="font-size: 12px; color: var(--text-muted);">Select Asset</label>
                        <select class="filter-select" id="backtest-symbol" style="width: 100%; margin-top: 5px;">
                            <option value="XAUUSD">XAUUSD (Gold)</option>
                            <option value="EURUSD">EURUSD</option>
                            <option value="GBPUSD">GBPUSD</option>
                            <option value="USDJPY">USDJPY</option>
                            <option value="AUDUSD">AUDUSD</option>
                        </select>
                    </div>
                    <div>
                        <label style="font-size: 12px; color: var(--text-muted);">Select Strategy</label>
                        <select class="filter-select" id="backtest-strategy" style="width: 100%; margin-top: 5px;">
                            <option value="scalping_strategy">Scalping SMC (M15)</option>
                            <option value="trend_following">Trend Following</option>
                            <option value="mean_reversion">Mean Reversion</option>
                            <option value="scalp_m5">Gold Scalp (M5)</option>
                        </select>
                    </div>
                    <div>
                        <label style="font-size: 12px; color: var(--text-muted);">Lookback Period</label>
                        <select class="filter-select" id="backtest-days" style="width: 100%; margin-top: 5px;">
                            <option value="7">Last 7 Days</option>
                            <option value="14">Last 14 Days</option>
                            <option value="30">Last 30 Days</option>
                        </select>
                    </div>
                    <button class="btn" id="run-backtest-btn" onclick="runHistoricalBacktest()" style="background: var(--primary); color: #fff; border-color: var(--primary); margin-top: 10px;"> Run Historical Backtest</button>
                </div>
            </div>

            <!-- Historical Backtest Results Curve -->
            <div class="card col-8">
                <h2>Historical Backtest Performance Results</h2>
                <div id="backtest-results-placeholder" style="text-align: center; padding: 50px 0; color: var(--text-muted);">
                    Select parameters and run the backtest to compile historical performance logs.
                </div>
                <div id="backtest-results-panel" style="display: none;">
                    <div style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 15px; margin-bottom: 20px;">
                        <div class="insight-box">
                            <div class="explainer-label">Net Profit</div>
                            <strong class="text-green" id="bt-net-profit">$0.00</strong>
                        </div>
                        <div class="insight-box">
                            <div class="explainer-label">Win Rate</div>
                            <strong id="bt-win-rate">0.0%</strong>
                        </div>
                        <div class="insight-box">
                            <div class="explainer-label">Total Trades</div>
                            <strong id="bt-total-trades">0</strong>
                        </div>
                        <div class="insight-box">
                            <div class="explainer-label">Profit Factor</div>
                            <strong id="bt-profit-factor">0.00</strong>
                        </div>
                        <div class="insight-box">
                            <div class="explainer-label">Max Drawdown</div>
                            <strong class="text-red" id="bt-max-drawdown">0.0%</strong>
                        </div>
                    </div>
                    <div id="backtest-equity-chart" style="min-height: 250px;"></div>
                </div>
            </div>"""

bt_start_idx = content.find("<!-- T7: BACKTEST & SIM -->")
if bt_start_idx != -1:
    card_idx = content.find(risk_sim_card_end, bt_start_idx)
    if card_idx != -1:
        content = content[:card_idx] + new_backtest_cards + content[card_idx + len(risk_sim_card_end):]
        print("SUCCESS: Injected backtest lab cards.")
    else:
        print("WARNING: Could not find closing Risk Scenario Simulator card.")
else:
    print("WARNING: Could not find simulators block.")

# 3. Add Javascript function runHistoricalBacktest()
bt_script = """        let btChart = null;
        async function runHistoricalBacktest() {
            const btn = document.getElementById('run-backtest-btn');
            const sym = document.getElementById('backtest-symbol').value;
            const strat = document.getElementById('backtest-strategy').value;
            const days = document.getElementById('backtest-days').value;
            
            btn.innerText = "Running Backtest...";
            btn.disabled = true;
            
            try {
                const res = await fetch(`/api/v1/advanced/backtest?symbol=${sym}&strategy=${strat}&days=${days}`);
                const data = await res.json();
                
                if (data.success && data.report) {
                    const r = data.report;
                    
                    document.getElementById('backtest-results-placeholder').style.display = 'none';
                    document.getElementById('backtest-results-panel').style.display = 'block';
                    
                    document.getElementById('bt-net-profit').innerText = `$${(r.net_pnl || 0).toFixed(2)}`;
                    document.getElementById('bt-net-profit').className = r.net_pnl >= 0 ? 'text-green' : 'text-red';
                    document.getElementById('bt-win-rate').innerText = `${(r.win_rate_pct || 0).toFixed(1)}%`;
                    document.getElementById('bt-total-trades').innerText = r.total_trades || 0;
                    document.getElementById('bt-profit-factor').innerText = (r.profit_factor || 0).toFixed(2);
                    document.getElementById('bt-max-drawdown').innerText = `${(r.max_drawdown_pct || 0).toFixed(1)}%`;
                    
                    const curve = r.equity_curve || [];
                    const eqData = curve.map(item => parseFloat(item.equity.toFixed(2)));
                    const categories = Array.from({length: eqData.length}, (_, i) => `T${i}`);
                    
                    const options = {
                        series: [{
                            name: 'Equity ($)',
                            data: eqData
                        }],
                        chart: {
                            type: 'area',
                            height: 220,
                            background: 'transparent',
                            foreColor: '#838fa7',
                            toolbar: { show: false }
                        },
                        colors: ['#00ffcc'],
                        stroke: {
                            curve: 'smooth',
                            width: 3
                        },
                        fill: {
                            type: 'gradient',
                            gradient: {
                                shadeIntensity: 1,
                                opacityFrom: 0.35,
                                opacityTo: 0.01,
                                stops: [0, 90, 100]
                            }
                        },
                        grid: {
                            borderColor: 'rgba(255, 255, 255, 0.05)',
                            strokeDashArray: 4
                        },
                        xaxis: {
                            categories: categories,
                            labels: { show: false }
                        },
                        yaxis: {
                            labels: {
                                formatter: function (val) {
                                    return "$" + val.toFixed(0);
                                }
                            }
                        },
                        tooltip: {
                            theme: 'dark'
                        }
                    };
                    
                    if (btChart) {
                        btChart.updateSeries([{ data: eqData }]);
                    } else {
                        btChart = new ApexCharts(document.querySelector("#backtest-equity-chart"), options);
                        btChart.render();
                    }
                } else {
                    alert("Backtest failed: " + (data.message || "Unknown error"));
                }
            } catch (e) {
                alert("Failed to execute backtest: " + e.message);
            } finally {
                btn.innerText = " Run Historical Backtest";
                btn.disabled = false;
            }
        }"""

close_script_idx = content.rfind("</script>")
if close_script_idx != -1:
    content = content[:close_script_idx] + bt_script + "\n\n" + content[close_script_idx:]
    print("SUCCESS: Injected backtest script logic.")
else:
    print("WARNING: Could not find closing script tag.")

with open(dashboard_path, "w", encoding="utf-8") as f:
    f.write(content)
print("SUCCESS: Saved dashboard.html.")
