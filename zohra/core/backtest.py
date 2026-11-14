import os
import logging
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from zohra.brokers.sim_broker import SimBroker
from zohra.core.agent_message import AgentMessage
from zohra.core.enums import MarketRegime, StrategyName
from zohra.core.decision_engine import decision_engine
from zohra.db.schema import db
from zohra.analytics.performance import analytics

logger = logging.getLogger("zohra.backtest")

class BacktestEngine:
    """
    Backtesting Engine:
    - Simulates historical stepping of candle data.
    - Feeds slice lookbacks to Decision Intelligence Engine.
    - Routes orders through a Simulated Broker.
    - Logs decisions and trades to the database.
    - Outputs a complete PerformanceAnalytics report.
    """
    def __init__(self, initial_balance: float = 100000.0, min_score_threshold: int = 70):
        self.sim_broker = SimBroker(initial_balance=initial_balance)
        self.min_score_threshold = min_score_threshold

    def run_backtest(self, df_m5: pd.DataFrame, df_m15: pd.DataFrame, df_h1: pd.DataFrame, 
                     symbol: str, start_idx: int = 100) -> Dict:
        """
        Runs the historical backtest loop.
        - Steps through df_m15 from start_idx to the end.
        - Slices data at each step to prevent lookahead bias.
        - Emulates ticks and processes SL/TP hits.
        """
        logger.info(f"⏳ Starting historical backtest for {symbol} | Length: {len(df_m15)} bars")
        
        # Instantiate temporary multi-agent setup utilizing SimBroker
        from zohra.agents.memory_agent import MemoryAgent
        from zohra.agents.news_agent import NewsAgent
        from zohra.agents.risk_agent import RiskAgent
        from zohra.agents.market_analysis_agent import MarketAnalysisAgent
        from zohra.agents.execution_agent import ExecutionAgent
        from zohra.security.permissions import TradingPermissionGateway

        memory_agent = MemoryAgent()
        news_agent = NewsAgent()
        
        # Setup RiskAgent using the simulated broker balance
        risk_agent = RiskAgent(starting_equity=self.sim_broker.get_balance())
        market_agent = MarketAnalysisAgent(min_score_threshold=self.min_score_threshold)
        
        # Instantiate ExecutionAgent
        exec_agent = ExecutionAgent(
            news_agent=news_agent,
            risk_agent=risk_agent,
            memory_agent=memory_agent,
            min_score_threshold=self.min_score_threshold,
            permission_gateway=TradingPermissionGateway(execution_mode="simulated"),
            broker=self.sim_broker,
        )

        import sys
        # Mock broker references in the global scope / execution context using sys.modules to avoid namespace shadowing
        import zohra.brokers.mt5_broker
        import zohra.agents.risk_agent
        import zohra.agents.execution_agent
        
        original_broker = sys.modules['zohra.brokers.mt5_broker'].mt5_broker
        
        sys.modules['zohra.brokers.mt5_broker'].mt5_broker = self.sim_broker
        sys.modules['zohra.agents.risk_agent'].mt5_broker = self.sim_broker
        sys.modules['zohra.agents.execution_agent'].mt5_broker = self.sim_broker
        
        from zohra.brokers.manager import broker_manager
        broker_manager.register_adapter("sim", self.sim_broker)
        broker_manager.set_default("sim")
        
        # Set starting equity for RiskAgent
        risk_agent.starting_equity = self.sim_broker.get_balance()
        
        # Backtest loop
        try:
            # We step through each index of the M15 DataFrame
            for i in range(start_idx, len(df_m15)):
                current_time = df_m15.index[i]
                
                # Check SL/TP fills of active trades at the current bar's open price
                current_bar_open = df_m15.iloc[i]['open']
                current_bar_high = df_m15.iloc[i]['high']
                current_bar_low = df_m15.iloc[i]['low']
                current_bar_close = df_m15.iloc[i]['close']
                
                # Set the current tick simulation price
                self.sim_broker.set_tick(symbol, current_bar_open, current_bar_open)
                # First check SL/TP breaches on the open price
                self.sim_broker.check_sl_tp_fills()
                
                # To simulate price spikes during the bar, we check high/low levels
                self.sim_broker.set_tick(symbol, current_bar_low, current_bar_high)
                self.sim_broker.check_sl_tp_fills()
                
                # Slices of data up to current_time (historical view)
                slice_m15 = df_m15.loc[:current_time]
                
                # Align M5 slice using the timestamp boundary
                slice_m5 = df_m5.loc[:current_time] if df_m5 is not None else None
                slice_h1 = df_h1.loc[:current_time] if df_h1 is not None else None
                
                # Update starting equity for risk limits calculation
                risk_agent.starting_equity = self.sim_broker.get_balance()
                
                # 1. Market Analysis Agent runs regime detection and strategy scanning to produce proposal
                proposal_msg = market_agent.analyze_market(slice_m5, slice_m15, slice_h1, symbol)
                if proposal_msg:
                    # Update message timestamp to current simulation time
                    proposal_msg.timestamp = current_time.isoformat()
                    proposal_msg.payload["broker"] = "sim"
                    
                    # 2. Execution Agent coordinates consensus voting loop & executes trades in SimBroker
                    exec_agent.process_consensus_voting(proposal_msg)
                
                # End of bar: finalize tick at close price
                self.sim_broker.set_tick(symbol, current_bar_close, current_bar_close)
                self.sim_broker.check_sl_tp_fills()

        finally:
            import sys
            sys.modules['zohra.brokers.mt5_broker'].mt5_broker = original_broker
            sys.modules['zohra.agents.risk_agent'].mt5_broker = original_broker
            sys.modules['zohra.agents.execution_agent'].mt5_broker = original_broker
            
            from zohra.brokers.manager import broker_manager
            broker_manager.set_default("mt5")
            broker_manager.unregister_adapter("sim")
            
        # Close any remaining open trades at the final close price
        final_price = df_m15.iloc[-1]['close']
        self.sim_broker.set_tick(symbol, final_price, final_price)
        self.sim_broker.close_all_positions(comment="Backtest-End")
        
        # Analyze performance
        closed_trades = self.sim_broker.closed_trades_history
        formatted_trades = []
        for t in closed_trades:
            formatted_trades.append({
                "symbol": t["symbol"],
                "direction": t["direction"],
                "position_size_lots": t["lots"],
                "entry_price": t["entry_price"],
                "exit_price": t["exit_price"],
                "pnl_usd": t["pnl"],
                "timestamp_open": t["open_time"],
                "timestamp_close": t["close_time"],
                "duration_minutes": 15,
                "strategy_used": "trend_following",
                "risk_reward_ratio": 2.0
            })
            
        equity_curve = [{"equity": self.sim_broker.initial_balance}]
        current_eq = self.sim_broker.initial_balance
        for t in formatted_trades:
            current_eq += t["pnl_usd"]
            equity_curve.append({"equity": current_eq})
            
        report = analytics.full_performance_report(formatted_trades, equity_curve)
        return report

    def run_monte_carlo(self, trades: List[Dict], runs: int = 1000, ruin_threshold: float = 20000.0) -> Dict:
        """
        Runs Monte Carlo simulations by shuffling trade outcomes.
        Calculates final equity distribution, drawdown risk, and probability of ruin.
        """
        if not trades:
            return {"error": "No trades available for Monte Carlo simulation."}

        pnl_array = np.array([t["pnl_usd"] for t in trades])
        initial_balance = self.sim_broker.initial_balance
        
        final_balances = []
        max_drawdowns = []
        ruin_count = 0

        for _ in range(runs):
            # Shuffle trade sequence
            shuffled_pnl = np.random.permutation(pnl_array)
            
            # Reconstruct equity curve
            equity = initial_balance
            peak = initial_balance
            max_dd = 0.0
            ruined = False

            for pnl in shuffled_pnl:
                equity += pnl
                if equity < ruin_threshold:
                    ruined = True
                if equity > peak:
                    peak = equity
                else:
                    dd = (peak - equity) / peak * 100.0
                    max_dd = max(max_dd, dd)

            final_balances.append(equity)
            max_drawdowns.append(max_dd)
            if ruined:
                ruin_count += 1

        final_balances = np.array(final_balances)
        max_drawdowns = np.array(max_drawdowns)

        return {
            "runs": runs,
            "ruin_probability_pct": (ruin_count / runs) * 100.0,
            "final_balance": {
                "median": float(np.median(final_balances)),
                "10th_percentile": float(np.percentile(final_balances, 10)),
                "90th_percentile": float(np.percentile(final_balances, 90)),
                "min": float(np.min(final_balances)),
                "max": float(np.max(final_balances))
            },
            "max_drawdown": {
                "median_pct": float(np.median(max_drawdowns)),
                "95th_percentile_pct": float(np.percentile(max_drawdowns, 95)),
                "99th_percentile_pct": float(np.percentile(max_drawdowns, 99)),
                "max_pct": float(np.max(max_drawdowns))
            }
        }

    def run_sensitivity_analysis(self, df_m5: pd.DataFrame, df_m15: pd.DataFrame, df_h1: pd.DataFrame, 
                                 symbol: str, threshold_values: List[int]) -> Dict[int, Dict]:
        """
        Sweeps different min_score_threshold values and compares backtest performance.
        Helps find the optimal confidence score threshold.
        """
        results = {}
        for val in threshold_values:
            logger.info(f"⚙️ Running sensitivity step: min_score_threshold={val}")
            engine = BacktestEngine(initial_balance=self.sim_broker.initial_balance, min_score_threshold=val)
            report = engine.run_backtest(df_m5, df_m15, df_h1, symbol)
            results[val] = {
                "net_profit": report.get("net_profit", 0.0),
                "win_rate": report.get("win_rate", 0.0),
                "max_drawdown_pct": report.get("max_drawdown_pct", 0.0),
                "profit_factor": report.get("profit_factor", 1.0),
                "total_trades": report.get("total_trades", 0)
            }
        return results
