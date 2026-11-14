# Zohra Bot B Startup Isolation Report
Date/Time: 2026-08-28T05:52:41.980756 UTC

## Isolation Parameters
- **Bot Name**: Bot B
- **Bot ID**: Zohra_bot_B
- **API Port**: 8004
- **MT5 Account**: 5055123669
- **MT5 Terminal Path**: C:\MetaTrader 5 B\terminal64.exe
- **Database Path**: logs/zohra_trades_b.db
- **Chroma Path**: logs/chroma_db_b
- **Journal CSV**: logs/zohra_journal_b.csv
- **Journal JSONL**: logs/decision_journal_b.jsonl
- **Rejected Log**: logs/rejected_trades_b.json
- **Weights File**: logs/strategy_weights_b.json
- **System Log**: logs/zohra_engine_b.log
- **Brain Log**: logs/zohra_brain_b.log

## Isolation Verification
- [x] **API/Dashboard/Websocket Port Isolation**: Confirmed bound to unique port 8004.
- [x] **MetaTrader 5 Binding**: Exclusive connection to Bot B verified. Desired path matches active terminal.
- [x] **Database Isolation**: Confirmed SQLite database isolated at `logs/zohra_trades_b.db`.
- [x] **Memory Vector DB Isolation**: Confirmed Chroma database isolated at `logs/chroma_db_b`.
- [x] **Journal/Log Isolation**: All output files configured with bot-specific suffix `_b` under logs directory.

**Status: COMPLETE ISOLATION VERIFIED**
