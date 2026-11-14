# Zohra Bot A (Trend Specialist) Startup Isolation Report
Date/Time: 2026-09-02T04:02:13.239854 UTC

## Isolation Parameters
- **Bot Name**: Bot A (Trend Specialist)
- **Bot ID**: BOT_1_TREND
- **API Port**: 8001
- **MT5 Account**: 10012413413
- **MT5 Terminal Path**: C:\MetaTrader 5 A\terminal64.exe
- **Database Path**: logs/zohra_trades_a.db
- **Chroma Path**: logs/chroma_db_a
- **Journal CSV**: logs/zohra_journal_a.csv
- **Journal JSONL**: logs/decision_journal_a.jsonl
- **Rejected Log**: logs/rejected_trades_a.json
- **Weights File**: logs/strategy_weights_a.json
- **System Log**: logs/zohra_engine_a.log
- **Brain Log**: logs/zohra_brain_a.log

## Isolation Verification
- [x] **API/Dashboard/Websocket Port Isolation**: Confirmed bound to unique port 8001.
- [x] **MetaTrader 5 Binding**: Exclusive connection to Bot A (Trend Specialist) verified. Desired path matches active terminal.
- [x] **Database Isolation**: Confirmed SQLite database isolated at `logs/zohra_trades_a.db`.
- [x] **Memory Vector DB Isolation**: Confirmed Chroma database isolated at `logs/chroma_db_a`.
- [x] **Journal/Log Isolation**: All output files configured with bot-specific suffix `_trend` under logs directory.

**Status: COMPLETE ISOLATION VERIFIED**
