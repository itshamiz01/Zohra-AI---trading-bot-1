# Zohra Bot A Startup Isolation Report
Date/Time: 2026-08-31T06:00:51.890433 UTC

## Isolation Parameters
- **Bot Name**: Bot A
- **Bot ID**: ZOHRA_BOT_A
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
- [x] **MetaTrader 5 Binding**: Exclusive connection to Bot A verified. Desired path matches active terminal.
- [x] **Database Isolation**: Confirmed SQLite database isolated at `logs/zohra_trades_a.db`.
- [x] **Memory Vector DB Isolation**: Confirmed Chroma database isolated at `logs/chroma_db_a`.
- [x] **Journal/Log Isolation**: All output files configured with bot-specific suffix `_a` under logs directory.

**Status: COMPLETE ISOLATION VERIFIED**
