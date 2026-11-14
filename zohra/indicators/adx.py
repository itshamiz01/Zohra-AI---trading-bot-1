import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple
from .atr import calculate_atr

def calculate_adx(df: pd.DataFrame, period: int = 14) -> Dict[str, Any]:
    """Calculates Average Directional Index (ADX, +DI, -DI)."""
    if df is None or len(df) < period + 1:
        return {"adx": pd.Series(), "plus_di": pd.Series(), "minus_di": pd.Series(),
                "latest_adx": 0.0, "latest_plus_di": 0.0, "latest_minus_di": 0.0}
    
    plus_dm = df['high'].diff()
    minus_dm = -df['low'].diff()
    plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0.0)
    minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0.0)
    
    atr = calculate_atr(df, period)
    plus_di = 100 * pd.Series(plus_dm, index=df.index).rolling(period).mean() / (atr + 1e-9)
    minus_di = 100 * pd.Series(minus_dm, index=df.index).rolling(period).mean() / (atr + 1e-9)
    
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
    adx = dx.rolling(period).mean()
    
    return {
        "adx": adx,
        "plus_di": plus_di,
        "minus_di": minus_di,
        "latest_adx": float(adx.iloc[-1]) if not np.isnan(adx.iloc[-1]) else 0.0,
        "latest_plus_di": float(plus_di.iloc[-1]) if not np.isnan(plus_di.iloc[-1]) else 0.0,
        "latest_minus_di": float(minus_di.iloc[-1]) if not np.isnan(minus_di.iloc[-1]) else 0.0
    }
