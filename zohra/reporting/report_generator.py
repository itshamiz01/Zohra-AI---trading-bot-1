"""
╔══════════════════════════════════════════════════════╗
║         ZOHRA — REPORTING DASHBOARD                  ║
║  Daily / Weekly / Monthly Reports with Charts        ║
╚══════════════════════════════════════════════════════╝

Generates:
  - Daily report (HTML + text summary for Telegram)
  - Weekly report (with equity curve chart)
  - Monthly report (full statistics + all charts)

Charts created:
  - Equity curve
  - Win/loss bar by pair
  - Session performance heatmap
  - Drawdown chart
  - Score distribution histogram
  - P&L distribution
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import LOG_DIR, REPORTS_DIR

logger = logging.getLogger("zohra.reporting")

# Try to import plotting libraries
try:
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.gridspec import GridSpec
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    logger.warning("matplotlib not installed — charts disabled. Run: pip install matplotlib")


class ReportGenerator:
    """
    Generates daily/weekly/monthly performance reports.
    Saves HTML files and sends summaries via Telegram.
    """

    def __init__(self):
        os.makedirs(REPORTS_DIR, exist_ok=True)
        self._style()

    def _style(self):
        """Apply dark chart style."""
        if MATPLOTLIB_AVAILABLE:
            plt.style.use('dark_background')

    # ─── DAILY REPORT ──────────────────────────────────────

    def generate_daily_report(self, report_data: Dict,
                               trades: List[Dict],
                               equity_curve: List[Dict]) -> str:
        """
        Generate full daily report.
        Returns path to HTML file.
        """
        date_str  = datetime.utcnow().strftime("%Y-%m-%d")
        report_dir = os.path.join(REPORTS_DIR, "daily")
        os.makedirs(report_dir, exist_ok=True)

        chart_path = None
        if MATPLOTLIB_AVAILABLE and equity_curve:
            chart_path = self._generate_equity_chart(
                equity_curve, f"daily_equity_{date_str}.png", title=f"Equity — {date_str}"
            )

        html = self._build_html_report(
            title=f"Zohra Daily Report — {date_str}",
            period="Daily",
            report_data=report_data,
            trades=trades,
            chart_path=chart_path,
        )

        output_path = os.path.join(report_dir, f"report_{date_str}.html")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        logger.info(f"📊 Daily report saved: {output_path}")
        return output_path

    def generate_weekly_report(self, report_data: Dict,
                                trades: List[Dict],
                                equity_curve: List[Dict]) -> str:
        """Generate weekly report with multiple charts."""
        week_str  = datetime.utcnow().strftime("%Y-W%U")
        report_dir = os.path.join(REPORTS_DIR, "weekly")
        os.makedirs(report_dir, exist_ok=True)

        chart_paths = []
        if MATPLOTLIB_AVAILABLE:
            if equity_curve:
                cp = self._generate_equity_chart(
                    equity_curve, f"weekly_equity_{week_str}.png",
                    title=f"Equity Curve — Week {week_str}"
                )
                if cp: chart_paths.append(cp)

            if trades:
                cp = self._generate_pair_pnl_chart(
                    trades, f"weekly_pairs_{week_str}.png",
                    title="P&L by Pair (Week)"
                )
                if cp: chart_paths.append(cp)

                cp = self._generate_session_chart(
                    trades, f"weekly_sessions_{week_str}.png",
                    title="Session Performance (Week)"
                )
                if cp: chart_paths.append(cp)

        html = self._build_html_report(
            title=f"Zohra Weekly Report — {week_str}",
            period="Weekly",
            report_data=report_data,
            trades=trades,
            chart_paths=chart_paths,
        )
        output_path = os.path.join(report_dir, f"report_{week_str}.html")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        logger.info(f"📊 Weekly report saved: {output_path}")
        return output_path

    def generate_monthly_report(self, report_data: Dict,
                                 trades: List[Dict],
                                 equity_curve: List[Dict]) -> str:
        """Generate full monthly report with all charts."""
        month_str  = datetime.utcnow().strftime("%Y-%m")
        report_dir = os.path.join(REPORTS_DIR, "monthly")
        os.makedirs(report_dir, exist_ok=True)

        chart_paths = []
        if MATPLOTLIB_AVAILABLE:
            generators = [
                (equity_curve, self._generate_equity_chart,
                 f"monthly_equity_{month_str}.png",    "Equity Curve — Month"),
                (trades,       self._generate_drawdown_chart,
                 f"monthly_dd_{month_str}.png",        "Drawdown"),
                (trades,       self._generate_pair_pnl_chart,
                 f"monthly_pairs_{month_str}.png",     "P&L by Pair"),
                (trades,       self._generate_session_chart,
                 f"monthly_sessions_{month_str}.png",  "Session Performance"),
                (trades,       self._generate_pnl_histogram,
                 f"monthly_hist_{month_str}.png",      "P&L Distribution"),
                (trades,       self._generate_score_distribution,
                 f"monthly_score_{month_str}.png",     "Confidence Score Distribution"),
            ]

            for data, fn, fname, title in generators:
                if data:
                    cp = fn(data, fname, title=title)
                    if cp: chart_paths.append(cp)

        html = self._build_html_report(
            title=f"Zohra Monthly Report — {month_str}",
            period="Monthly",
            report_data=report_data,
            trades=trades,
            chart_paths=chart_paths,
        )
        output_path = os.path.join(report_dir, f"report_{month_str}.html")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        # Also save JSON snapshot
        json_path = os.path.join(report_dir, f"snapshot_{month_str}.json")
        safe_data = {k: v for k, v in report_data.items()
                     if not isinstance(v, dict) or k not in ('session_stats','pair_stats','strategy_stats','regime_stats')}
        with open(json_path, 'w') as f:
            json.dump(safe_data, f, indent=2, default=str)

        logger.info(f"📊 Monthly report saved: {output_path}")
        return output_path

    # ─── Telegram Summary ──────────────────────────────────

    def build_telegram_summary(self, report_data: Dict, period: str = "Daily") -> str:
        """Build concise Telegram message from report data."""
        wr     = report_data.get('win_rate', 0)
        pf     = report_data.get('profit_factor', 0)
        exp    = report_data.get('expectancy', 0)
        pnl    = report_data.get('total_pnl', 0)
        trades = report_data.get('total_trades', 0)
        wins   = report_data.get('winning_trades', 0)
        losses = report_data.get('losing_trades', 0)
        dd_pct = report_data.get('max_drawdown_pct', 0)
        sharpe = report_data.get('sharpe_ratio', 0)
        best_p = report_data.get('best_pair', '—')
        worst_p = report_data.get('worst_pair', '—')

        emoji_pnl = "🟢" if pnl >= 0 else "🔴"
        pnl_str   = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"

        msg = (
            f"╔════════════════════╗\n"
            f"║  📊 ZOHRA {period.upper()} REPORT  ║\n"
            f"╚════════════════════╝\n\n"
            f"{emoji_pnl} <b>P&L: {pnl_str}</b>\n\n"
            f"📈 Win Rate: <b>{wr:.1f}%</b> ({wins}W / {losses}L)\n"
            f"⚖️ Profit Factor: <b>{pf:.2f}</b>\n"
            f"💰 Expectancy: <b>${exp:.2f}/trade</b>\n"
            f"📉 Max DD: <b>{dd_pct:.2f}%</b>\n"
            f"📊 Sharpe: <b>{sharpe:.2f}</b>\n\n"
            f"🔢 Total Trades: {trades}\n"
            f"🏆 Best Pair: {best_p}\n"
            f"⚠️ Worst Pair: {worst_p}\n\n"
            f"⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC"
        )
        return msg

    # ─── Chart Generators ──────────────────────────────────

    def _generate_equity_chart(self, equity_curve: List[Dict],
                                filename: str, title: str = "Equity") -> Optional[str]:
        if not MATPLOTLIB_AVAILABLE or not equity_curve:
            return None

        path = os.path.join(REPORTS_DIR, filename)
        try:
            times    = [e.get('timestamp', '')[:19] for e in equity_curve]
            equities = [float(e.get('equity', 0)) for e in equity_curve]

            fig, ax = plt.subplots(figsize=(14, 5))
            color = '#00d4aa'
            ax.plot(range(len(equities)), equities, color=color, linewidth=2)
            ax.fill_between(range(len(equities)), equities,
                            min(equities), alpha=0.15, color=color)
            ax.set_title(title, fontsize=14, pad=12, color='white')
            ax.set_ylabel("Equity ($)", color='white')
            ax.set_facecolor('#1a1a2e')
            fig.patch.set_facecolor('#16213e')
            ax.tick_params(colors='gray')
            ax.grid(True, alpha=0.15, color='gray')
            plt.tight_layout()
            plt.savefig(path, dpi=120, bbox_inches='tight', facecolor=fig.get_facecolor())
            plt.close(fig)
            return path
        except Exception as e:
            logger.error(f"Equity chart error: {e}")
            return None

    def _generate_pair_pnl_chart(self, trades: List[Dict],
                                  filename: str, title: str = "P&L by Pair") -> Optional[str]:
        if not MATPLOTLIB_AVAILABLE:
            return None

        path = os.path.join(REPORTS_DIR, filename)
        try:
            pair_pnl: Dict[str, float] = {}
            for t in trades:
                sym = t.get('symbol', 'UNK')
                pair_pnl[sym] = pair_pnl.get(sym, 0) + (t.get('pnl_usd') or 0)

            if not pair_pnl:
                return None

            pairs  = list(pair_pnl.keys())
            pnls   = list(pair_pnl.values())
            colors = ['#00d4aa' if p >= 0 else '#ff6b6b' for p in pnls]

            fig, ax = plt.subplots(figsize=(12, 5))
            bars = ax.bar(pairs, pnls, color=colors, edgecolor='none', width=0.6)
            ax.axhline(0, color='gray', linewidth=0.8, alpha=0.5)
            ax.set_title(title, fontsize=13, pad=10, color='white')
            ax.set_ylabel("P&L ($)", color='white')
            ax.set_facecolor('#1a1a2e')
            fig.patch.set_facecolor('#16213e')
            ax.tick_params(colors='gray')
            ax.grid(True, axis='y', alpha=0.15, color='gray')
            for bar, val in zip(bars, pnls):
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                        f"${val:.0f}", ha='center', va='bottom',
                        fontsize=8, color='white')
            plt.tight_layout()
            plt.savefig(path, dpi=120, bbox_inches='tight', facecolor=fig.get_facecolor())
            plt.close(fig)
            return path
        except Exception as e:
            logger.error(f"Pair chart error: {e}")
            return None

    def _generate_session_chart(self, trades: List[Dict],
                                 filename: str, title: str = "Session Performance") -> Optional[str]:
        if not MATPLOTLIB_AVAILABLE:
            return None

        path = os.path.join(REPORTS_DIR, filename)
        try:
            sess_pnl: Dict[str, float] = {}
            sess_wr:  Dict[str, List]  = {}
            for t in trades:
                sess = t.get('session', 'Unknown') or 'Unknown'
                pnl  = t.get('pnl_usd') or 0
                sess_pnl[sess] = sess_pnl.get(sess, 0) + pnl
                sess_wr.setdefault(sess, []).append(1 if pnl > 0 else 0)

            if not sess_pnl:
                return None

            sessions = list(sess_pnl.keys())
            pnls     = list(sess_pnl.values())
            wrs      = [sum(sess_wr[s]) / len(sess_wr[s]) * 100 for s in sessions]
            colors   = ['#00d4aa' if p >= 0 else '#ff6b6b' for p in pnls]

            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

            ax1.bar(sessions, pnls, color=colors)
            ax1.set_title("P&L by Session", color='white')
            ax1.set_ylabel("P&L ($)", color='white')
            ax1.set_facecolor('#1a1a2e')
            ax1.tick_params(colors='gray')
            ax1.grid(True, axis='y', alpha=0.15, color='gray')
            ax1.axhline(0, color='gray', linewidth=0.8)

            ax2.bar(sessions, wrs, color='#4ecdc4')
            ax2.axhline(50, color='gray', linewidth=0.8, linestyle='--', alpha=0.5)
            ax2.set_title("Win Rate by Session", color='white')
            ax2.set_ylabel("Win Rate (%)", color='white')
            ax2.set_ylim(0, 100)
            ax2.set_facecolor('#1a1a2e')
            ax2.tick_params(colors='gray')
            ax2.grid(True, axis='y', alpha=0.15, color='gray')

            fig.patch.set_facecolor('#16213e')
            fig.suptitle(title, fontsize=13, color='white')
            plt.tight_layout()
            plt.savefig(path, dpi=120, bbox_inches='tight', facecolor=fig.get_facecolor())
            plt.close(fig)
            return path
        except Exception as e:
            logger.error(f"Session chart error: {e}")
            return None

    def _generate_drawdown_chart(self, trades: List[Dict],
                                  filename: str, title: str = "Drawdown") -> Optional[str]:
        if not MATPLOTLIB_AVAILABLE:
            return None

        path = os.path.join(REPORTS_DIR, filename)
        try:
            # Build equity series from cumulative PnL
            pnls  = [t.get('pnl_usd') or 0 for t in trades if t.get('pnl_usd') is not None]
            equity = []
            running = 0
            for p in pnls:
                running += p
                equity.append(running)

            if not equity:
                return None

            # Drawdown series
            peak = equity[0]
            dd   = []
            for eq in equity:
                if eq > peak: peak = eq
                dd.append(eq - peak)

            fig, ax = plt.subplots(figsize=(14, 4))
            ax.fill_between(range(len(dd)), dd, 0, alpha=0.7, color='#ff6b6b')
            ax.plot(range(len(dd)), dd, color='#ff4444', linewidth=1)
            ax.set_title(title, fontsize=13, color='white')
            ax.set_ylabel("Drawdown ($)", color='white')
            ax.set_facecolor('#1a1a2e')
            fig.patch.set_facecolor('#16213e')
            ax.tick_params(colors='gray')
            ax.grid(True, alpha=0.15, color='gray')
            plt.tight_layout()
            plt.savefig(path, dpi=120, bbox_inches='tight', facecolor=fig.get_facecolor())
            plt.close(fig)
            return path
        except Exception as e:
            logger.error(f"Drawdown chart error: {e}")
            return None

    def _generate_pnl_histogram(self, trades: List[Dict],
                                 filename: str, title: str = "P&L Distribution") -> Optional[str]:
        if not MATPLOTLIB_AVAILABLE:
            return None

        path = os.path.join(REPORTS_DIR, filename)
        try:
            pnls = [t.get('pnl_usd') or 0 for t in trades if t.get('pnl_usd') is not None]
            if not pnls:
                return None

            fig, ax = plt.subplots(figsize=(10, 5))
            ax.hist([p for p in pnls if p > 0], bins=20, color='#00d4aa', alpha=0.7, label='Wins')
            ax.hist([p for p in pnls if p < 0], bins=20, color='#ff6b6b', alpha=0.7, label='Losses')
            ax.axvline(0, color='white', linewidth=1, linestyle='--')
            ax.set_title(title, fontsize=13, color='white')
            ax.set_xlabel("P&L ($)", color='white')
            ax.set_ylabel("Count", color='white')
            ax.legend(facecolor='#1a1a2e', edgecolor='gray', labelcolor='white')
            ax.set_facecolor('#1a1a2e')
            fig.patch.set_facecolor('#16213e')
            ax.tick_params(colors='gray')
            ax.grid(True, alpha=0.15, color='gray')
            plt.tight_layout()
            plt.savefig(path, dpi=120, bbox_inches='tight', facecolor=fig.get_facecolor())
            plt.close(fig)
            return path
        except Exception as e:
            logger.error(f"P&L histogram error: {e}")
            return None

    def _generate_score_distribution(self, trades: List[Dict],
                                      filename: str, title: str = "Score Distribution") -> Optional[str]:
        if not MATPLOTLIB_AVAILABLE:
            return None

        path = os.path.join(REPORTS_DIR, filename)
        try:
            scores = [t.get('confidence_score') or 0 for t in trades
                      if t.get('confidence_score') is not None]
            if not scores:
                return None

            fig, ax = plt.subplots(figsize=(10, 5))
            ax.hist(scores, bins=20, color='#7c5cbf', alpha=0.85, edgecolor='none')
            ax.axvline(65, color='#ffd700', linewidth=1.5, linestyle='--', label='Min score (65)')
            ax.axvline(95, color='#00d4aa', linewidth=1.5, linestyle='--', label='A+ threshold (95)')
            ax.set_title(title, fontsize=13, color='white')
            ax.set_xlabel("Confidence Score", color='white')
            ax.set_ylabel("Trade Count", color='white')
            ax.legend(facecolor='#1a1a2e', edgecolor='gray', labelcolor='white')
            ax.set_facecolor('#1a1a2e')
            fig.patch.set_facecolor('#16213e')
            ax.tick_params(colors='gray')
            ax.grid(True, alpha=0.15, color='gray')
            plt.tight_layout()
            plt.savefig(path, dpi=120, bbox_inches='tight', facecolor=fig.get_facecolor())
            plt.close(fig)
            return path
        except Exception as e:
            logger.error(f"Score chart error: {e}")
            return None

    # ─── HTML Builder ──────────────────────────────────────

    def _build_html_report(self, title: str, period: str,
                            report_data: Dict, trades: List[Dict],
                            chart_path: str = None,
                            chart_paths: List[str] = None) -> str:
        """Build premium dark-mode HTML report."""
        all_charts = []
        if chart_path: all_charts.append(chart_path)
        if chart_paths: all_charts.extend(chart_paths)

        def fmt(val, prefix="$", suffix="", decimals=2):
            if val is None: return "—"
            return f"{prefix}{val:.{decimals}f}{suffix}"

        def badge(val, good_threshold=0, bad_threshold=0, prefix=""):
            if val is None: return '<span class="badge neutral">—</span>'
            color = "good" if val >= good_threshold else ("bad" if val <= bad_threshold else "neutral")
            return f'<span class="badge {color}">{prefix}{val:.2f}</span>'

        wr    = report_data.get('win_rate', 0)
        pnl   = report_data.get('total_pnl', 0)
        pf    = report_data.get('profit_factor', 0)
        exp   = report_data.get('expectancy', 0)
        sharpe = report_data.get('sharpe_ratio', 0)
        dd_pct = report_data.get('max_drawdown_pct', 0)
        total = report_data.get('total_trades', 0)
        wins  = report_data.get('winning_trades', 0)
        losses = report_data.get('losing_trades', 0)

        # Recent trades table
        recent = sorted(trades, key=lambda t: t.get('timestamp_close', ''), reverse=True)[:20]
        trade_rows = ""
        for t in recent:
            p     = t.get('pnl_usd') or 0
            color = "#00d4aa" if p >= 0 else "#ff6b6b"
            trade_rows += f"""
            <tr>
                <td>{(t.get('timestamp_close') or '')[:16]}</td>
                <td><b>{t.get('symbol','')}</b></td>
                <td>{t.get('direction','')}</td>
                <td>{t.get('strategy_used','')}</td>
                <td>{t.get('session','')}</td>
                <td>{t.get('confidence_score','—')}</td>
                <td>{t.get('quality_grade','—')}</td>
                <td style="color:{color};font-weight:bold">${p:.2f}</td>
                <td>{t.get('exit_reason_code','')}</td>
            </tr>"""

        # Charts HTML
        charts_html = ""
        for cp in all_charts:
            if cp and os.path.exists(cp):
                charts_html += f'<div class="chart"><img src="{cp}" alt="chart" /></div>\n'

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  :root {{
    --bg: #0f0f1a; --card: #1a1a2e; --border: #2a2a4a;
    --text: #e0e0e0; --dim: #888; --accent: #00d4aa;
    --good: #00d4aa; --bad: #ff6b6b; --warn: #ffd700;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', sans-serif; background: var(--bg);
         color: var(--text); padding: 20px; }}
  h1 {{ font-size: 1.8rem; color: var(--accent); margin-bottom: 4px; }}
  .subtitle {{ color: var(--dim); font-size: 0.9rem; margin-bottom: 24px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
           gap: 12px; margin-bottom: 24px; }}
  .kpi {{ background: var(--card); border: 1px solid var(--border);
          border-radius: 10px; padding: 16px; text-align: center; }}
  .kpi .val {{ font-size: 1.6rem; font-weight: 700; margin: 6px 0; }}
  .kpi .lbl {{ font-size: 0.75rem; color: var(--dim); text-transform: uppercase; }}
  .good {{ color: var(--good); }}
  .bad  {{ color: var(--bad); }}
  .warn {{ color: var(--warn); }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px;
            font-size: 0.8rem; font-weight: 600; }}
  .badge.good {{ background: rgba(0,212,170,0.15); color: var(--good); }}
  .badge.bad  {{ background: rgba(255,107,107,0.15); color: var(--bad);  }}
  .badge.neutral {{ background: #333; color: var(--dim); }}
  .chart {{ background: var(--card); border: 1px solid var(--border);
            border-radius: 10px; padding: 12px; margin-bottom: 16px; overflow: hidden; }}
  .chart img {{ width: 100%; border-radius: 6px; }}
  table {{ width: 100%; border-collapse: collapse; background: var(--card);
           border-radius: 10px; overflow: hidden; border: 1px solid var(--border); }}
  th {{ background: #252540; color: var(--dim); font-size: 0.75rem;
        text-transform: uppercase; padding: 10px 12px; text-align: left; }}
  td {{ padding: 9px 12px; font-size: 0.85rem; border-top: 1px solid var(--border); }}
  tr:hover td {{ background: rgba(255,255,255,0.03); }}
  .section-title {{ font-size: 1.1rem; color: var(--accent); margin: 20px 0 10px; }}
  footer {{ color: var(--dim); font-size: 0.75rem; text-align: center; margin-top: 30px; }}
</style>
</head>
<body>
<h1>🤖 {title}</h1>
<p class="subtitle">Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC | Period: {period}</p>

<!-- KPI Grid -->
<div class="grid">
  <div class="kpi">
    <div class="lbl">Net P&L</div>
    <div class="val {'good' if pnl >= 0 else 'bad'}">${pnl:+.2f}</div>
  </div>
  <div class="kpi">
    <div class="lbl">Win Rate</div>
    <div class="val {'good' if wr >= 50 else 'bad'}">{wr:.1f}%</div>
    <div style="font-size:0.78rem;color:var(--dim)">{wins}W / {losses}L</div>
  </div>
  <div class="kpi">
    <div class="lbl">Profit Factor</div>
    <div class="val {'good' if pf >= 1.5 else 'bad'}">{pf:.2f}</div>
  </div>
  <div class="kpi">
    <div class="lbl">Expectancy</div>
    <div class="val {'good' if exp >= 0 else 'bad'}">${exp:.2f}</div>
  </div>
  <div class="kpi">
    <div class="lbl">Sharpe Ratio</div>
    <div class="val {'good' if sharpe >= 1 else 'warn' if sharpe >= 0 else 'bad'}">{sharpe:.2f}</div>
  </div>
  <div class="kpi">
    <div class="lbl">Max Drawdown</div>
    <div class="val {'bad' if dd_pct > 5 else 'warn'}">{dd_pct:.2f}%</div>
  </div>
  <div class="kpi">
    <div class="lbl">Total Trades</div>
    <div class="val">{total}</div>
  </div>
  <div class="kpi">
    <div class="lbl">Avg Duration</div>
    <div class="val">{report_data.get('avg_duration_minutes', 0):.0f}m</div>
  </div>
</div>

<!-- Charts -->
{charts_html}

<!-- Recent Trades -->
<div class="section-title">📋 Recent Trades</div>
<table>
  <thead>
    <tr>
      <th>Close Time</th><th>Symbol</th><th>Dir</th><th>Strategy</th>
      <th>Session</th><th>Score</th><th>Grade</th><th>P&L</th><th>Exit</th>
    </tr>
  </thead>
  <tbody>{trade_rows}</tbody>
</table>

<footer>Zohra AI Trading Engine — MetaTrader 5 | {datetime.utcnow().year}</footer>
</body>
</html>"""
        return html


# Singleton
report_generator = ReportGenerator()
