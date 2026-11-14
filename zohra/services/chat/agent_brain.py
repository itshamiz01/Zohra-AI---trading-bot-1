# zohra/services/chat/agent_brain.py
import os
import json
import logging
import asyncio
from typing import AsyncGenerator, Dict, Any, List
import zohra.config.settings as settings
from zohra.services.chat.conversation_memory import conversation_memory
from zohra.services.chat.vector_memory import vector_memory
from zohra.services.chat.tool_calling import TOOL_REGISTRY
from zohra.services.chat.reflection_engine import reflection_engine

logger = logging.getLogger("zohra.services.chat.brain")

# OpenRouter & Groq AI Providers

SYSTEM_INSTRUCTION = """You are **Zohra AI**, the elite autonomous trading partner, risk chairman, and research analyst of the Zohra Quant Desk.

## OPERATIONAL GUIDELINES:
1. **Fact-Grounded Reasoning:** You have direct access to system database tools. Never guess, make up, or hallucinate stats (e.g. balance, trades, win rates, drawdown). If a tool is unavailable, say so honestly.
2. **ReAct Paradigm:** Analyze user requests by performing a Chain-of-Thought reasoning loop:
   - Identify what data is needed.
   - Select and invoke the proper tool.
   - Analyze the tool observations.
   - Refine your planning or execute more tools if needed.
   - Formulate a transparent, data-supported final response.
3. **Tone & Personality:** Professional, authoritative, quantitative, and precise. Use technical terms like Order Blocks, Liquidity Sweeps, expectancies, and pips accurately.
4. **Safety Overrides:** If the user asks you to modify risk limits or close positions, inform them that you are executing the change, and request they verify the update on their control dashboard.
5. **Memory Usage:** Retrieve relevant historical discussions or user preferences when answering.
6. **Historical Intelligence Engine (HIE):** You have access to HIE database tools: `query_hie_pattern_stats`, `get_hie_symbol_profile`, `query_hie_similarity`, and `get_hie_failure_patterns`. Use them to study past setups, check symbol performance intelligence, check trade similarity, and retrieve recurring losing combinations (failure patterns).
"""

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_account_positions",
            "description": "Get current MT5 account parameters (balance, equity, free margin, floating profit) and list all active/open positions with their ticket numbers, entry prices, and current PnL.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_trade_journal",
            "description": "Queries historical closed trades and post-mortem notes from the database. Optionally filter by a specific MT5 ticket ID or currency symbol (e.g. 'XAUUSD', 'EURUSD').",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket": {"type": "integer", "description": "Optional ticket ID to query"},
                    "symbol": {"type": "string", "description": "Optional currency symbol to query"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_performance_analytics",
            "description": "Query system performance statistics aggregated over the last N days (e.g. 7, 30, 90). Includes total trades, win rate percentage, profit factor, net PnL, expectancy, and max drawdown.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Number of days to aggregate performance metrics for. Defaults to 30."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scan_market_regimes",
            "description": "Check current technical indicators and market structure regime for a specific symbol (e.g. 'EURUSD', 'XAUUSD'). Returns ADX trend strength, Bollinger Bands width, and trend direction.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Currency symbol to scan (e.g. 'EURUSD', 'XAUUSD')"}
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_system_status",
            "description": "Verify Zohra's operational state. Includes connected broker status, daily drawdown values, trading halt flags, and economic news blackout alerts.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_long_term_memories",
            "description": "Query long-term AI memory and past user instruction files for relevant context. Use this to recall past agreements, trade reasons, and strategy insights.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query_text": {"type": "string", "description": "Semantic query search term"}
                },
                "required": ["query_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "modify_risk_setting",
            "description": "Updates the system risk per trade configuration setting to a new percentage value. The new value must be between 0.1% and 5.0%.",
            "parameters": {
                "type": "object",
                "properties": {
                    "risk_pct": {"type": "number", "description": "New risk percentage value (e.g., 1.5)"}
                },
                "required": ["risk_pct"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "close_active_positions",
            "description": "Triggers an emergency closing of open positions. action_type must be either 'ALL' (exit everything) or 'PROFITABLE' (exit winning trades only).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action_type": {"type": "string", "enum": ["ALL", "PROFITABLE"], "description": "Action type: ALL or PROFITABLE"}
                },
                "required": ["action_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_hie_pattern_stats",
            "description": "Queries statistical historical pattern performance stats from the HIE Pattern Library. Optionally filter by symbol, setup_type, session, direction, or timeframe.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Optional currency symbol"},
                    "setup_type": {"type": "string", "description": "Optional setup type, e.g. 'BOS', 'FVG'"},
                    "session": {"type": "string", "description": "Optional session, e.g. 'London', 'NewYork'"},
                    "direction": {"type": "string", "description": "Optional direction, e.g. 'LONG', 'SHORT'"},
                    "timeframe": {"type": "string", "description": "Optional timeframe"},
                    "min_occurrences": {"type": "integer", "description": "Minimum occurrences, defaults to 5"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_hie_symbol_profile",
            "description": "Query the Symbol Intelligence Profile and Market Memory Summary for a specific symbol. Returns the symbol's best/worst session, best/worst timeframe, win rate, and average R-multiple.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Symbol name (e.g. 'EURUSD')"}
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_hie_similarity",
            "description": "Find historically similar past setups and return their win rate, average R-multiple, and evidence.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Symbol name (e.g. 'EURUSD')"},
                    "direction": {"type": "string", "description": "Direction: LONG or SHORT"},
                    "session": {"type": "string", "description": "Session name"},
                    "setup_type": {"type": "string", "description": "Optional setup type"}
                },
                "required": ["symbol", "direction", "session"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_hie_failure_patterns",
            "description": "Retrieve flagged recurring losing patterns and failure setups detected by the Failure Pattern Detector.",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]

class AgenticBrain:
    """
    Agentic Brain coordinating intent, tool execution, long-term memory retrieval,
    ReAct reasoning chains, and pre-response reflection audits.
    """
    def __init__(self):
        self.provider = getattr(settings, "CHAT_PROVIDER", "openrouter").lower()
        self.openrouter_model_name = getattr(settings, "OPENROUTER_MODEL", "openai/gpt-4o-mini")
        self.groq_model_name = getattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile")
        logger.info(f"Agent brain initialized with provider: {self.provider} (OpenRouter model: {self.openrouter_model_name})")

    def get_openai_history(self, session_id: str) -> List[Dict[str, Any]]:
        raw_history = conversation_memory.get_history(session_id)
        formatted = []
        if raw_history and raw_history[0].get("id", 0) > raw_history[-1].get("id", 0):
            raw_history = list(reversed(raw_history))
            
        for msg in raw_history:
            role = msg.get("role", "user")
            role = "assistant" if role in ("assistant", "bot", "model") else "user"
            content = msg.get("message", "")
            if not content:
                continue
            formatted.append({"role": role, "content": content})
        return formatted

    async def run_reasoning_loop(self, session_id: str, prompt: str) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Runs the ReAct reasoning loop. Yields streaming updates:
        - {"type": "thought", "content": "Thought description..."}
        - {"type": "tool", "name": "tool_name", "args": {...}}
        - {"type": "token", "content": "Markdown token..."}
        """
        # 1. Retrieve long-term memory context to inject
        mem_context = vector_memory.query_semantic_memories(prompt, limit=2)
        
        # Save user message to DB
        conversation_memory.add_message(session_id, "user", prompt)
        
        # Build prompt incorporating long-term memories
        enhanced_prompt = prompt
        if mem_context:
            enhanced_prompt = f"{mem_context}\nUser query: {prompt}"

        # Determine if we should use OpenRouter or Groq
        use_openrouter = (self.provider == "openrouter" and bool(settings.OPENROUTER_API_KEY)) or (bool(settings.OPENROUTER_API_KEY) and not (self.provider == "groq" and settings.GROQ_API_KEY))
        use_groq = (self.provider == "groq" and bool(settings.GROQ_API_KEY)) or (bool(settings.GROQ_API_KEY) and not use_openrouter)
        
        # If no LLM is configured, fallback to command parser/routing
        if not use_openrouter and not use_groq:
            logger.warning("No LLM API keys configured. Falling back to local NLU.")
            yield {"type": "thought", "content": "⚠️ LLM API keys missing. Falling back to local template routing..."}
            from zohra.services.chat.intent_layer import intent_recognizer
            from zohra.services.chat.command_router import command_router
            
            intent, params = intent_recognizer.parse(prompt, [])
            yield {"type": "thought", "content": f"Intent parsed: {intent}. Executing command..."}
            res_text, res_data = command_router.dispatch(intent, params, prompt)
            yield {"type": "tool", "name": "NLU Router", "intent": intent, "args": params, "raw_data": res_data}
            for i in range(0, len(res_text), 15):
                yield {"type": "token", "content": res_text[i:i+15]}
                await asyncio.sleep(0.001)
            conversation_memory.add_message(session_id, "assistant", res_text, intent=intent)
            return

        final_text_response = ""

        if use_openrouter:
            # ═══ OPENROUTER REACT LOOP ═══
            import requests
            history = self.get_openai_history(session_id)
            messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}] + history + [{"role": "user", "content": enhanced_prompt}]
            
            loop_count = 0
            max_loops = 5
            
            yield {"type": "thought", "content": f"Analyzing trading query with OpenRouter ({self.openrouter_model_name}) brain..."}
            
            try:
                while loop_count < max_loops:
                    loop_count += 1
                    
                    url = "https://openrouter.ai/api/v1/chat/completions"
                    headers = {
                        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://github.com/ZohraQuant/trading_bot",
                        "X-Title": "Zohra AI Command Center"
                    }
                    payload = {
                        "model": self.openrouter_model_name,
                        "messages": messages,
                        "tools": OPENAI_TOOLS,
                        "tool_choice": "auto",
                        "temperature": 0.2
                    }
                    
                    response = await asyncio.to_thread(
                        requests.post,
                        url, headers=headers, json=payload, timeout=15
                    )
                    response.raise_for_status()
                    resp_json = response.json()
                    
                    choice_msg = resp_json["choices"][0]["message"]
                    tool_calls = choice_msg.get("tool_calls")
                    
                    # Append assistant message exactly as returned
                    messages.append(choice_msg)
                    
                    if not tool_calls:
                        final_text_response = choice_msg.get("content") or ""
                        break
                        
                    for call in tool_calls:
                        call_id = call["id"]
                        tool_name = call["function"]["name"]
                        args_str = call["function"]["arguments"]
                        
                        try:
                            args = json.loads(args_str) if args_str else {}
                        except Exception:
                            args = {}
                            
                        yield {"type": "thought", "content": f"Executing quantitative tool: {tool_name}({json.dumps(args)})"}
                        yield {"type": "tool", "name": tool_name, "args": args}
                        
                        tool_func = TOOL_REGISTRY.get(tool_name)
                        if not tool_func:
                            observation = f"Error: Tool '{tool_name}' not registered."
                        else:
                            try:
                                observation = await asyncio.to_thread(tool_func, **args)
                            except Exception as ex:
                                observation = f"Error executing tool: {ex}"
                                
                        # Append tool response
                        messages.append({
                            "role": "tool",
                            "tool_call_id": call_id,
                            "name": tool_name,
                            "content": observation
                        })
                        
                        yield {"type": "thought", "content": "Analyzing tool outputs and generating next thought..."}
                        
            except Exception as e:
                logger.error(f"Error in OpenRouter reasoning loop: {e}")
                yield {"type": "thought", "content": f"⚠️ OpenRouter request failed: {e}. Falling back..."}
                # Fallback to local template
                from zohra.services.chat.intent_layer import intent_recognizer
                from zohra.services.chat.command_router import command_router
                intent, params = intent_recognizer.parse(prompt, [])
                final_text_response, _ = command_router.dispatch(intent, params, prompt)

        elif use_groq:
            # ═══ GROQ REACT LOOP ═══
            import requests
            history = self.get_openai_history(session_id)
            messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}] + history + [{"role": "user", "content": enhanced_prompt}]
            
            loop_count = 0
            max_loops = 5
            
            yield {"type": "thought", "content": "Analyzing trading query with Groq Llama brain..."}
            
            try:
                while loop_count < max_loops:
                    loop_count += 1
                    
                    url = "https://api.groq.com/openai/v1/chat/completions"
                    headers = {
                        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "model": self.groq_model_name,
                        "messages": messages,
                        "tools": OPENAI_TOOLS,
                        "tool_choice": "auto",
                        "temperature": 0.2
                    }
                    
                    response = await asyncio.to_thread(
                        requests.post,
                        url, headers=headers, json=payload, timeout=15
                    )
                    response.raise_for_status()
                    resp_json = response.json()
                    
                    choice_msg = resp_json["choices"][0]["message"]
                    tool_calls = choice_msg.get("tool_calls")
                    
                    # Append assistant message exactly as returned (crucial for tool sequence continuity)
                    messages.append(choice_msg)
                    
                    if not tool_calls:
                        final_text_response = choice_msg.get("content") or ""
                        break
                        
                    for call in tool_calls:
                        call_id = call["id"]
                        tool_name = call["function"]["name"]
                        args_str = call["function"]["arguments"]
                        
                        try:
                            args = json.loads(args_str) if args_str else {}
                        except Exception:
                            args = {}
                            
                        yield {"type": "thought", "content": f"Executing quantitative tool: {tool_name}({json.dumps(args)})"}
                        yield {"type": "tool", "name": tool_name, "args": args}
                        
                        tool_func = TOOL_REGISTRY.get(tool_name)
                        if not tool_func:
                            observation = f"Error: Tool '{tool_name}' not registered."
                        else:
                            try:
                                observation = await asyncio.to_thread(tool_func, **args)
                            except Exception as ex:
                                observation = f"Error executing tool: {ex}"
                                
                        # Append tool response
                        messages.append({
                            "role": "tool",
                            "tool_call_id": call_id,
                            "name": tool_name,
                            "content": observation
                        })
                        
                        yield {"type": "thought", "content": "Analyzing tool outputs and generating next thought..."}
                        
            except Exception as e:
                logger.error(f"Error in Groq reasoning loop: {e}")
                yield {"type": "thought", "content": f"⚠️ Groq request failed: {e}. Falling back..."}
                # Fallback to local template
                from zohra.services.chat.intent_layer import intent_recognizer
                from zohra.services.chat.command_router import command_router
                intent, params = intent_recognizer.parse(prompt, [])
                final_text_response, _ = command_router.dispatch(intent, params, prompt)

        else:
            # Fallback to local template router
            from zohra.services.chat.intent_layer import intent_recognizer
            from zohra.services.chat.command_router import command_router
            intent, params = intent_recognizer.parse(prompt, [])
            final_text_response, _ = command_router.dispatch(intent, params, prompt)

        try:
            # 4. Reflection Engine Self-Audit
            yield {"type": "thought", "content": "Running post-audit reflection checks to verify facts..."}
            ref_verdict = reflection_engine.audit_response(enhanced_prompt, final_text_response)
            if not ref_verdict.get("passed", True):
                yield {"type": "thought", "content": "⚠️ Reflection check flagged assumption. Rerunning reasoning..."}
                final_text_response += f"\n\n*Self-Reflection Correction: {ref_verdict.get('correction')}*"

            # Yield the final answer tokens
            yield {"type": "thought", "content": "Debrief formulated successfully."}
            
            for i in range(0, len(final_text_response), 15):
                chunk = final_text_response[i:i+15]
                yield {"type": "token", "content": chunk}
                await asyncio.sleep(0.001)

            # Store assistant answer in database
            conversation_memory.add_message(session_id, "assistant", final_text_response)
            
            if any(w in prompt.lower() for w in ("remember", "risk", "strategy", "loss", "win", "optimize")):
                vector_memory.add_preference_or_insight(
                    text=f"User query: {prompt} | Zohra AI analysis: {final_text_response}",
                    category="interaction"
                )
                
        except Exception as e:
            logger.error(f"Error in formatting final response: {e}")
            yield {"type": "error", "content": f"Agentic loop error: {str(e)}"}

# Singleton
agentic_brain = AgenticBrain()
