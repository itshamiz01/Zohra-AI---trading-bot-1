# ZOHRA OS — Cost Optimizer
import logging
import time
from typing import Dict, Any, List

logger = logging.getLogger("zohra.evolution.cost")

class CostRecord:
    def __init__(self, model: str, input_tokens: int, output_tokens: int, cost: float):
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cost = cost
        self.timestamp = time.time()

class CostOptimizer:
    """Tracks token consumption, calculates API expenditures, and recommends optimizations."""
    def __init__(self):
        self.records: List[CostRecord] = []
        logger.info("Cost Optimizer loaded.")

    def log_inference(self, model: str, input_tokens: int, output_tokens: int):
        # Pricing per 1M tokens (simulated)
        pricing = {
            "gemini-3.5-flash": {"input": 0.075, "output": 0.30},
            "groq-llama-3.3": {"input": 0.20, "output": 0.20},
            "local-llama-onnx": {"input": 0.0, "output": 0.0}
        }
        
        rates = pricing.get(model.lower(), {"input": 0.15, "output": 0.60})
        cost = ((input_tokens / 1_000_000) * rates["input"]) + ((output_tokens / 1_000_000) * rates["output"])
        
        record = CostRecord(model, input_tokens, output_tokens, cost)
        self.records.append(record)
        logger.debug(f"Logged inference cost: ${cost:.6f} for model {model}")

    def get_accumulated_costs(self) -> Dict[str, float]:
        """Returns total costs and token consumption."""
        total_cost = sum(r.cost for r in self.records)
        total_tokens = sum(r.input_tokens + r.output_tokens for r in self.records)
        
        return {
            "total_cost_usd": float(round(total_cost, 4)),
            "total_tokens_consumed": total_tokens,
            "cost_today_usd": float(round(total_cost, 4)) # For simplicity in stubs
        }
