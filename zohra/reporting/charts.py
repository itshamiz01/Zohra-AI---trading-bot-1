"""Chart generation for performance reports."""

from pathlib import Path
from typing import Dict, List, Optional

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


def _parse_times(equity_curve: List[Dict]) -> tuple:
    times, values = [], []
    for point in equity_curve:
        ts = point.get("timestamp") or point.get("time")
        eq = point.get("equity", 0)
        if ts:
            from datetime import datetime
            try:
                times.append(datetime.fromisoformat(str(ts).replace("Z", "")))
                values.append(float(eq))
            except (ValueError, TypeError):
                continue
    return times, values


def plot_equity_curve(equity_curve: List[Dict], output_path: str, title: str = "Equity Curve"):
    if not MATPLOTLIB_AVAILABLE or not equity_curve:
        return None

    times, values = _parse_times(equity_curve)
    if not times:
        return None

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(times, values, color="#2563eb", linewidth=1.5)
    ax.fill_between(times, values, alpha=0.1, color="#2563eb")
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_ylabel("Equity ($)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=120)
    plt.close()
    return output_path


def plot_pnl_by_group(
    group_data: Dict[str, Dict],
    output_path: str,
    title: str = "P&L by Group",
    key_label: str = "Group",
):
    if not MATPLOTLIB_AVAILABLE or not group_data:
        return None

    labels = list(group_data.keys())[:12]
    values = [group_data[k].get("net_pnl", 0) for k in labels]
    colors = ["#16a34a" if v >= 0 else "#dc2626" for v in values]

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.barh(labels, values, color=colors)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_xlabel("Net P&L ($)")
    ax.axvline(0, color="#64748b", linewidth=0.8)
    plt.tight_layout()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=120)
    plt.close()
    return output_path


def plot_win_rate_pie(metrics: Dict, output_path: str):
    if not MATPLOTLIB_AVAILABLE:
        return None

    wins = metrics.get("winning_trades", 0)
    losses = metrics.get("losing_trades", 0)
    if wins + losses == 0:
        return None

    fig, ax = plt.subplots(figsize=(5, 5))
    ax.pie(
        [wins, losses],
        labels=[f"Wins ({wins})", f"Losses ({losses})"],
        colors=["#16a34a", "#dc2626"],
        autopct="%1.1f%%",
        startangle=90,
    )
    ax.set_title(f"Win Rate: {metrics.get('win_rate_pct', 0)}%")
    plt.tight_layout()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=120)
    plt.close()
    return output_path
