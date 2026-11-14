import logging
import json
import re
import requests
from typing import List, Dict, Any, Tuple, Optional
import zohra.config.settings as settings

logger = logging.getLogger("zohra.services.chat.intent")

SYSTEM_PROMPT = """
You are the Natural Language Understanding (NLU) component of the Zohra Autonomous Trading Engine Command Center.
Your job is to parse the user's input message and conversation history, classify the user's request into one of the Command Center intent categories, and extract its parameters.

You MUST respond ONLY with a JSON object containing the keys "intent" and "parameters". Do not add any conversational text before or after the JSON.

Supported intents and parameters:

1. TRADING_QUERY: Check open trades, balance, equity, or trigger control actions (halt, resume, close positions, change risk).
   - Parameters:
     * "action" (string, optional): "get_positions", "close_all", "close_profitable", "halt", "resume", "modify_risk".
     * "reason" (string, optional): Reason for halting.
     * "risk_pct" (float, optional): New risk percentage (e.g. 0.5, 1.5).

2. ANALYTICS_QUERY: Check performance stats, win rates, profit factor, drawdown, expectancy, or strategy rankings.
   - Parameters:
     * "days" (integer, optional): The history length in days. Default is 30.

3. JOURNAL_QUERY: Query closed trades history, post-mortem notes, confluences, or explain specific trade wins/losses.
   - Parameters:
     * "symbol" (string, optional): E.g. "XAUUSD", "EURUSD"
     * "ticket" (integer, optional): MT5 ticket ID

4. MEMORY_QUERY: Query or store long-term memories, user preferences, trade lessons, or notes.
   - Parameters:
     * "query_text" (string, required): Semantic search query or note to store.
     * "action" (string, optional): "search", "store". Default is "search".

5. RESEARCH_QUERY: Analyze market trends (ADX, Bollinger Bands), check symbol intelligence profile, or query historical similarity.
   - Parameters:
     * "symbol" (string, optional): E.g. "XAUUSD"
     * "direction" (string, optional): "LONG" or "SHORT"
     * "session" (string, optional): "London", "NewYork", "Asian"

6. TASK_QUERY: Create system tasks, show task checklists, update tasks status.
   - Parameters:
     * "action" (string, required): "create", "list", "complete"
     * "title" (string, optional): Task title
     * "task_id" (integer, optional): ID of the task to update

7. SYSTEM_QUERY: Monitor CPU, RAM, database health, MT5 connection status, and API health.
   - Parameters: none.

8. FILE_QUERY: Read or list project workspace files, reports, logs, and config sheets.
   - Parameters:
     * "action" (string, optional): "read", "list"
     * "file_path" (string, optional): Relative path of the file to read (e.g. "requirements.txt", "logs/zohra_engine_c.log")

9. LEARNING_QUERY: Query failure pattern database, outcome calibrations, or strategy optimization recommendations.
   - Parameters: none.

10. BACKTEST_QUERY: Run historical backtests, Monte Carlo simulations, sensitivity sweeps, or open market replay.
    - Parameters:
      * "action" (string, optional): "run_backtest", "run_replay", "monte_carlo", "sensitivity".
      * "symbol" (string, optional): E.g. "XAUUSD"

11. SOCIAL_MEDIA_QUERY: Social media content generation, calendar updates, and planning.
    - Parameters:
      * "platform" (string, required): "instagram", "youtube", "x", "linkedin"
      * "topic" (string, optional): Topic of content
      * "content_type" (string, optional): "post", "script", "caption"

12. BUSINESS_QUERY: Email manager drafts, lead tracking, publisher outreach updates.
    - Parameters:
      * "action" (string, required): "draft_email", "list_outreach", "log_contact"
      * "recipient" (string, optional): Recipient email or name
      * "subject" (string, optional): Subject line
      * "body_prompt" (string, optional): Prompt details for draft content

13. PERSONAL_QUERY: Productivity management (notes vault, reminders calendar, project goal tracker).
    - Parameters:
      * "action" (string, required): "add_note", "list_notes", "schedule_reminder", "list_reminders", "add_goal", "list_goals"
      * "title" (string, optional): Title for note
      * "content" (string, optional): Text details for note/reminder/goal
      * "due_at" (string, optional): Due date/time string

14. INFRASTRUCTURE_QUERY: Infrastructure and operations commands — service health, backups, restarts, model costs, deployment history.
    - Parameters:
      * "action" (string, optional): "health_report", "backup", "restore", "restart_service", "stop_service", "list_backups", "cost_report", "list_services"
      * "service_id" (string, optional): ID of the service to control (e.g. "trading_core", "research_engine")
      * "backup_file" (string, optional): Filename of the backup archive to restore

15. GENERAL_QUERY: Greet the AI, ask general trading theory, generic Q&A.
    - Parameters:
      * "query" (string): Raw question text.

16. ENGINE_CONTROL: Start, stop, or check status of specific market engines (forex, indian, crypto).
    - Use when the user asks to run, start, stop, enable, disable, or check the status of market engines.
    - Parameters:
      * "action" (string, required): "start", "stop", "status"
      * "engines" (list of strings, optional): List of engine names to act upon. Valid values: "forex", "indian", "crypto".
        If omitted with "start", start all engines. If omitted with "status", show all.
    - Example user messages:
      * "Run only forex market engine" → {"intent": "ENGINE_CONTROL", "parameters": {"action": "start", "engines": ["forex"]}}
      * "Run only Indian market engine" → {"intent": "ENGINE_CONTROL", "parameters": {"action": "start", "engines": ["indian"]}}
      * "Run only crypto market engine" → {"intent": "ENGINE_CONTROL", "parameters": {"action": "start", "engines": ["crypto"]}}
      * "Run forex and crypto engines" → {"intent": "ENGINE_CONTROL", "parameters": {"action": "start", "engines": ["forex", "crypto"]}}
      * "Run all engines" → {"intent": "ENGINE_CONTROL", "parameters": {"action": "start", "engines": ["forex", "indian", "crypto"]}}
      * "Stop crypto engine" → {"intent": "ENGINE_CONTROL", "parameters": {"action": "stop", "engines": ["crypto"]}}
      * "What engines are running?" → {"intent": "ENGINE_CONTROL", "parameters": {"action": "status"}}
"""

class IntentRecognizer:
    """
    Parses natural language user inputs to extract structured intents and parameters.
    """

    def parse(self, message: str, context: List[Dict[str, str]] = None) -> Tuple[str, Dict[str, Any]]:
        cleaned_msg = message.strip()
        
        # Try Groq API first
        if settings.GROQ_API_KEY:
            try:
                intent, params = self._query_groq(cleaned_msg, context or [])
                if intent:
                    return intent, params
            except Exception as e:
                logger.warning(f"Groq intent parse failed, falling back to regex: {e}")
        
        return self._parse_regex(cleaned_msg)

    def _query_groq(self, message: str, context: List[Dict[str, str]]) -> Tuple[str, Dict[str, Any]]:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in context[-5:]:
            messages.append(msg)
        messages.append({"role": "user", "content": message})
        
        payload = {
            "model": settings.GROQ_MODEL,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0.0,
            "max_tokens": 150
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=5)
        response.raise_for_status()
        
        data = response.json()
        raw_content = data["choices"][0]["message"]["content"]
        
        parsed = json.loads(raw_content)
        intent = parsed.get("intent")
        parameters = parsed.get("parameters", {})
        
        if intent:
            return intent, parameters
        raise ValueError("Invalid format returned by LLM")

    def _parse_regex(self, message: str) -> Tuple[str, Dict[str, Any]]:
        msg = message.lower().strip()
        
        # 1. Social Media Queries
        if any(w in msg for w in ["social media", "instagram", "youtube", "post on x", "tweet", "linkedin", "caption", "hashtag", "script idea"]):
            platform = "instagram"
            if "youtube" in msg:
                platform = "youtube"
            elif "linkedin" in msg:
                platform = "linkedin"
            elif "x" in msg or "tweet" in msg:
                platform = "x"
            content_type = "post"
            if "script" in msg:
                content_type = "script"
            elif "caption" in msg:
                content_type = "caption"
            return "SOCIAL_MEDIA_QUERY", {"platform": platform, "topic": message, "content_type": content_type}

        # 2. Business Queries
        if any(w in msg for w in ["email", "draft pitch", "publisher", "outreach", "log contact", "submission"]):
            action = "list_outreach"
            if "email" in msg or "draft" in msg:
                action = "draft_email"
                return "BUSINESS_QUERY", {"action": action, "recipient": "recipient@example.com", "subject": "Update", "body_prompt": message}
            if "log" in msg or "contact" in msg:
                action = "log_contact"
                return "BUSINESS_QUERY", {"action": action, "recipient": "New Publisher", "notes": message}
            return "BUSINESS_QUERY", {"action": action}

        # 3. Personal Productivity Queries
        if any(w in msg for w in ["remind", "note", "goal"]):
            action = "list_notes"
            if "remind" in msg:
                action = "schedule_reminder"
                rem_match = re.search(r"remind\s+me\s+to\s+(.+)", msg)
                content = rem_match.group(1) if rem_match else message
                return "PERSONAL_QUERY", {"action": action, "content": content.capitalize(), "due_at": "Tomorrow"}
            if "note" in msg:
                if "add" in msg or "create" in msg or "save" in msg:
                    action = "add_note"
                    note_match = re.search(r"(?:add|create|save)(?:\s+note)?\s+about\s+(.+)", msg)
                    content = note_match.group(1) if note_match else message
                    return "PERSONAL_QUERY", {"action": action, "title": "New Note", "content": content.capitalize()}
                return "PERSONAL_QUERY", {"action": "list_notes"}
            if "goal" in msg:
                if "add" in msg or "create" in msg or "set" in msg:
                    action = "add_goal"
                    goal_match = re.search(r"(?:add|create|set)(?:\s+goal)?\s+to\s+(.+)", msg)
                    content = goal_match.group(1) if goal_match else message
                    return "PERSONAL_QUERY", {"action": action, "content": content.capitalize()}
                return "PERSONAL_QUERY", {"action": "list_goals"}

        # 4. Trading Commands (close positions, risk adjustment, halt, resume)
        if "close" in msg and "profitable" in msg:
            return "CLOSE_PROFITABLE", {}
        if "close" in msg and ("all" in msg or "emergency" in msg or "everything" in msg):
            return "CLOSE_ALL", {}
        if any(p in msg for p in ["halt trading", "pause trading", "stop trading", "stop the bot", "pause the bot", "halt the engine", "stop scanning"]):
            reason = "Manual halt requested via chat."
            match = re.search(r"because\s+(.+)", msg)
            if match:
                reason = match.group(1)
            return "HALT_TRADING", {"reason": reason}
        if any(p in msg for p in ["resume", "start trading", "continue trading", "start the bot", "resume scanning", "unpause"]):
            return "RESUME_TRADING", {}
        if "risk" in msg and ("set" in msg or "reduce" in msg or "increase" in msg or "change" in msg or "to" in msg):
            match = re.search(r"(\d+(\.\d+)?)\s*%", msg)
            if not match:
                match = re.search(r"(\d+(\.\d+)?)", msg)
            if match:
                try:
                    risk_val = float(match.group(1))
                    if risk_val < 0.05 and "%" not in msg:
                        risk_val = risk_val * 100.0
                    return "MODIFY_RISK", {"risk_pct": risk_val}
                except ValueError:
                    pass
        if any(w in msg for w in ["open position", "active trade", "positions", "what's open", "current trade", "balance", "equity", "account", "margin"]):
            if "closed" not in msg and "history" not in msg and "performance" not in msg:
                return "GET_POSITIONS", {}

        # 5. Tasks Commands (system tasks, not personal)
        if "task" in msg:
            action = "list"
            if "create" in msg or "add" in msg:
                action = "create"
                title_match = re.search(r"(?:create|add)(?:\s+task)?\s+to\s+(.+)", msg)
                title = title_match.group(1) if title_match else "New Task via Chat"
                return "TASK_QUERY", {"action": action, "title": title.capitalize()}
            if "complete" in msg or "done" in msg:
                action = "complete"
                id_match = re.search(r"\b\d+\b", msg)
                task_id = int(id_match.group(0)) if id_match else 0
                return "TASK_QUERY", {"action": action, "task_id": task_id}
            return "TASK_QUERY", {"action": "list"}

        # 6. File system queries
        if any(w in msg for w in ["file", "read", "view", "show logs", "show log", "system.log"]):
            action = "list"
            file_path = None
            if "requirements" in msg:
                action = "read"
                file_path = "requirements.txt"
            elif "log" in msg:
                action = "read"
                file_path = "logs/zohra_engine_c.log"
            return "FILE_QUERY", {"action": action, "file_path": file_path}

        # 7. System Health queries
        if any(w in msg for w in ["system health", "cpu", "ram", "server", "hardware", "how healthy", "health of system"]):
            return "SYSTEM_QUERY", {}

        # 8. Backtest & Replay queries
        if any(w in msg for w in ["backtest", "replay", "monte carlo", "sensitivity"]):
            action = "run_backtest"
            if "replay" in msg:
                action = "run_replay"
            elif "monte" in msg:
                action = "monte_carlo"
            elif "sensitivity" in msg:
                action = "sensitivity"
            symbol = self._extract_symbol(msg) or "XAUUSD"
            return "BACKTEST_QUERY", {"action": action, "symbol": symbol}

        # 9. Performance / Analytics
        perf_keywords = ["performance", "win rate", "profit factor", "expectancy", "drawdown", "stats", "today", "weekly", "monthly", "p&l", "pnl", "yesterday"]
        if any(w in msg for w in perf_keywords):
            days = 30
            if "week" in msg:
                days = 7
            elif "month" in msg:
                days = 30
            elif "today" in msg or "daily" in msg:
                days = 1
            elif "yesterday" in msg:
                days = 2
            return "GET_PERFORMANCE", {"days": days}

        # 10. Journal queries
        symbol = self._extract_symbol(msg)
        if any(w in msg for w in ["why", "explain", "reason", "reject", "skip", "veto", "fail", "pass", "why not", "didn't take"]):
            params = {}
            if symbol:
                params["symbol"] = symbol
            ticket_match = re.search(r"\b\d{9,12}\b", msg)
            if ticket_match:
                params["ticket"] = int(ticket_match.group(0))
            if "reject" in msg or "skip" in msg or "veto" in msg or "fail" in msg or "didn't take" in msg:
                return "EXPLAIN_REJECTION", params
            return "EXPLAIN_TRADE", params

        # 10. Learning queries
        if any(w in msg for w in ["failure pattern", "losing setup", "losing pattern", "losing combo", "recommendation", "learn", "what did we learn"]):
            return "LEARNING_QUERY", {}

        # 11. Research Queries
        if any(w in msg for w in ["analyze", "analysis", "market scan", "regime", "profile", "work best", "works best", "similarity"]):
            return "ANALYZE_MARKET", {"symbol": symbol or "XAUUSD"}

        # 12. Timeline Queries
        if "timeline" in msg or "milestone" in msg or "history of events" in msg:
            return "TIMELINE_QUERY", {}

        # 12. Memory Queries
        if "remember" in msg or "memory" in msg or "preferences" in msg:
            action = "search"
            if "remember" in msg or "save" in msg or "store" in msg:
                action = "store"
            return "MEMORY_QUERY", {"query_text": message, "action": action}

        # 13. Engine Control Queries
        engine_keywords = ["engine", "market engine"]
        if any(w in msg for w in engine_keywords):
            engines = []
            if "forex" in msg or "fx" in msg:
                engines.append("forex")
            if "indian" in msg or "india" in msg or "nse" in msg or "bse" in msg or "dhan" in msg:
                engines.append("indian")
            if "crypto" in msg or "bitcoin" in msg or "btc" in msg or "coindcx" in msg:
                engines.append("crypto")
            if "all" in msg and not engines:
                engines = ["forex", "indian", "crypto"]

            if any(w in msg for w in ["stop", "disable", "shut down", "turn off", "kill"]):
                return "ENGINE_CONTROL", {"action": "stop", "engines": engines or ["forex", "indian", "crypto"]}
            elif any(w in msg for w in ["status", "running", "what", "which", "check", "list"]):
                return "ENGINE_CONTROL", {"action": "status", "engines": engines}
            else:
                # Default: "run", "start", "enable", "activate", "turn on", or just mentioning engine names
                return "ENGINE_CONTROL", {"action": "start", "engines": engines or ["forex", "indian", "crypto"]}

        # 14. General QNA Fallback
        return "GENERAL_QUERY", {"query": message}

    def _extract_symbol(self, message: str) -> Optional[str]:
        lowered = message.lower()
        if "gold" in lowered or "xau" in lowered or "xauusd" in lowered:
            return "XAUUSD"
        match = re.search(r"\b((?:eur|usd|gbp|jpy|aud|nzd|cad|chf|xau|xag){2})\b", lowered)
        if match:
            return match.group(1).upper()
        return None

intent_recognizer = IntentRecognizer()
