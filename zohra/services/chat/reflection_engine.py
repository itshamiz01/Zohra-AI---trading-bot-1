# zohra/services/chat/reflection_engine.py
import logging
import json
import zohra.config.settings as settings

logger = logging.getLogger("zohra.services.chat.reflection")

# OpenRouter & Groq AI Providers

class ReflectionEngine:
    """
    Reflection Engine:
    - Post-processing validator auditing AI-generated debriefings and reports.
    - Evaluates responses against the fact payload to prevent hallucinations.
    """
    def should_store_memory(self, query: str, response_text: str) -> bool:
        import re
        return bool(response_text.strip() and re.search(r"\b(remember|preference|lesson|learned)\b", query, re.I))

    def audit_response(self, query: str, response_text: str) -> dict:
        """
        Runs a quick critique check. Returns {'passed': True} or {'passed': False, 'correction': '...'}
        """
        provider = getattr(settings, "CHAT_PROVIDER", "openrouter").lower()
        use_openrouter = (provider == "openrouter" and bool(settings.OPENROUTER_API_KEY)) or (bool(settings.OPENROUTER_API_KEY) and not (provider == "groq" and settings.GROQ_API_KEY))
        use_groq = (provider == "groq" and bool(settings.GROQ_API_KEY)) or (bool(settings.GROQ_API_KEY) and not use_openrouter)

        if not use_openrouter and not use_groq:
            return {"passed": True}
            
        prompt = (
            f"You are the Zohra Self-Reflection Critic auditing a generated assistant reply.\n\n"
            f"User Query: \"{query}\"\n"
            f"Generated Reply: \"{response_text}\"\n\n"
            f"Evaluate if the reply makes explicit factual assumptions, guesses metrics, or states numbers that "
            f"lack logical validation from the user's account state.\n"
            f"If the reply is completely accurate and contains no hallucinations or assumptions, return:\n"
            f"{{\"passed\": true}}\n"
            f"If you find an assumption or unverified number, return:\n"
            f"{{\"passed\": false, \"correction\": \"A brief correction statement highlighting the ungrounded detail.\"}}\n"
        )

        if use_openrouter:
            import requests
            try:
                url = "https://openrouter.ai/api/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/ZohraQuant/trading_bot",
                    "X-Title": "Zohra AI Command Center"
                }
                payload = {
                    "model": getattr(settings, "OPENROUTER_MODEL", "openai/gpt-4o-mini"),
                    "messages": [
                        {"role": "system", "content": "You are the Zohra Self-Reflection Critic auditing a generated assistant reply. Return ONLY a valid JSON object matching the requested schema: {\"passed\": boolean, \"correction\": string}."},
                        {"role": "user", "content": prompt}
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1
                }
                response = requests.post(url, headers=headers, json=payload, timeout=10)
                response.raise_for_status()
                res_content = response.json()["choices"][0]["message"]["content"]
                return json.loads(res_content)
            except Exception as e:
                logger.warning(f"Self-reflection check via OpenRouter failed: {e}. Passing by default.")
                return {"passed": True}

        if use_groq:
            import requests
            try:
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": getattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile"),
                    "messages": [
                        {"role": "system", "content": "You are the Zohra Self-Reflection Critic auditing a generated assistant reply. Return ONLY a valid JSON object matching the requested schema: {\"passed\": boolean, \"correction\": string}."},
                        {"role": "user", "content": prompt}
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1
                }
                response = requests.post(url, headers=headers, json=payload, timeout=10)
                response.raise_for_status()
                res_content = response.json()["choices"][0]["message"]["content"]
                return json.loads(res_content)
            except Exception as e:
                logger.warning(f"Self-reflection check via Groq failed: {e}. Passing by default.")
                return {"passed": True}
        return {"passed": True}

# Singleton
reflection_engine = ReflectionEngine()
