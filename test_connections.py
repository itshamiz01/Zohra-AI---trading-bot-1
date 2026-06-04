import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv, set_key
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

ENV_FILE = os.path.join(os.path.dirname(__file__), '.env')

print('=' * 50)
print('TRADING BOT - FULL CONNECTIVITY TEST')
print('=' * 50)

# ── 1. ENV VARS ──────────────────────────────────
print()
print('[1/4] Checking .env credentials...')
from config import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GROQ_API_KEY, GROQ_MODEL

print(f'  MT5 Login  : {MT5_LOGIN}')
print(f'  MT5 Server : {MT5_SERVER}')
print(f'  MT5 Pass   : {"*" * len(MT5_PASSWORD)} ({len(MT5_PASSWORD)} chars)')
print(f'  Telegram   : {"SET" if TELEGRAM_BOT_TOKEN else "NOT SET"}')
print(f'  Telegram ID: {TELEGRAM_CHAT_ID}')
print(f'  Groq Model : {GROQ_MODEL}')
print(f'  Groq Key   : {"SET" if GROQ_API_KEY else "NOT SET"}')
print('  OK')

# ── 2. MT5 CONNECTION ────────────────────────────
print()
print('[2/4] Testing MetaTrader 5 connection...')
try:
    import MetaTrader5 as mt5
    if mt5.initialize():
        authorized = mt5.login(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
        if authorized:
            info = mt5.account_info()
            print('  CONNECTED to MT5!')
            print(f'     Name    : {info.name}')
            print(f'     Balance : {info.balance:.2f} {info.currency}')
            print(f'     Equity  : {info.equity:.2f} {info.currency}')
            print(f'     Server  : {info.server}')
            print(f'     Leverage: 1:{info.leverage}')
            # Fetch a live EURUSD candle
            import pandas as pd
            rates = mt5.copy_rates_from_pos('EURUSD', 16385, 0, 3)
            if rates is not None and len(rates) > 0:
                df = pd.DataFrame(rates)
                df['time'] = pd.to_datetime(df['time'], unit='s')
                print(f'     Live EURUSD close: {df["close"].iloc[-1]:.5f}')
        else:
            print(f'  LOGIN FAILED: {mt5.last_error()}')
        mt5.shutdown()
    else:
        err = mt5.last_error()
        print(f'  MT5 NOT RUNNING: {err}')
        print()
        print('  ACTION REQUIRED:')
        print('  1. Download MT5: https://www.metatrader5.com/en/download')
        print('  2. Install and open it')
        print('  3. Go to File -> Open an Account -> MetaQuotes-Demo')
        print('  4. Log in with your credentials')
        print('  5. Run this test again')
except Exception as e:
    print(f'  Exception: {e}')

# ── 3. TELEGRAM ──────────────────────────────────
print()
print('[3/4] Testing Telegram bot...')
import requests

try:
    r = requests.get(
        f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe',
        timeout=10
    )
    if r.status_code == 200:
        bot = r.json()['result']
        print(f'  Bot token VALID!')
        print(f'     Bot: @{bot["username"]}')

        # Find chat ID from updates
        r2 = requests.get(
            f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates',
            timeout=10
        )
        if r2.status_code == 200:
            updates = r2.json().get('result', [])
            if updates:
                # Get the most recent user message
                found_id = None
                for upd in reversed(updates):
                    msg = upd.get('message', {})
                    chat = msg.get('chat', {})
                    if chat.get('type') in ('private', 'group', 'supergroup'):
                        found_id = chat.get('id')
                        name = chat.get('first_name', chat.get('title', ''))
                        break

                if found_id:
                    print(f'  Found your Chat ID: {found_id} ({name})')
                    # Auto-update .env if it was wrong
                    if str(TELEGRAM_CHAT_ID) != str(found_id):
                        set_key(ENV_FILE, 'TELEGRAM_CHAT_ID', str(found_id))
                        print(f'  Auto-fixed TELEGRAM_CHAT_ID in .env -> {found_id}')

                    # Send a test message
                    r3 = requests.post(
                        f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage',
                        json={
                            'chat_id': found_id,
                            'text': '<b>Trading Bot Connected!</b>\nAll systems go. Bot is ready to trade.',
                            'parse_mode': 'HTML'
                        },
                        timeout=10
                    )
                    if r3.status_code == 200:
                        print('  Test message SENT to Telegram! Check your chat.')
                    else:
                        print(f'  Message send failed: {r3.text[:100]}')
            else:
                print()
                print('  ACTION REQUIRED:')
                print('  1. Open Telegram on your phone or PC')
                print('  2. Search for @Tradingwithhamiz_bot')
                print('  3. Send it any message (e.g. /start or "hello")')
                print('  4. Run this test again — it will auto-detect and fix your chat ID')
    else:
        print(f'  Bot token INVALID ({r.status_code})')
except Exception as e:
    print(f'  Exception: {e}')

# ── 4. GROQ LLM ──────────────────────────────────
print()
print('[4/4] Testing Groq LLM...')
try:
    r4 = requests.post(
        'https://api.groq.com/openai/v1/chat/completions',
        headers={
            'Authorization': f'Bearer {GROQ_API_KEY}',
            'Content-Type': 'application/json'
        },
        json={
            'model': GROQ_MODEL,
            'messages': [{'role': 'user', 'content': 'Reply with just the word OK'}],
            'max_tokens': 5
        },
        timeout=15
    )
    if r4.status_code == 200:
        reply = r4.json()['choices'][0]['message']['content']
        print(f'  Groq LLM WORKING! Model: {GROQ_MODEL}')
        print(f'  Response: "{reply.strip()}"')
    else:
        print(f'  Groq FAILED {r4.status_code}: {r4.text[:200]}')
except Exception as e:
    print(f'  Exception: {e}')

print()
print('=' * 50)
print('TEST COMPLETE')
print('=' * 50)
