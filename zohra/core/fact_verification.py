"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA — FACT VERIFICATION ENGINE                   ║
║         Cross-Reference Analysis & Claim Confidence Scoring          ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger("zohra.research.verification")

class FactVerificationEngine:
    """
    Evaluates the validity of research findings by cross-referencing claims
    across multiple sources (e.g. academic papers, web search, local memory).
    """
    def verify_claim(self, claim: str, sources: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Cross-references a claim against a list of sources.
        Returns a confidence rating and verification status.
        """
        claim_lower = claim.lower()
        matches = []
        confidence = 0.3 # Base level for unverified claim
        
        for src in sources:
            text_to_check = ""
            if "summary" in src:
                text_to_check = src["summary"].lower()
            elif "raw_content" in src:
                text_to_check = src["raw_content"].lower()
                
            # Check for keyword overlap
            keywords = [w for w in claim_lower.split() if len(w) > 4]
            overlap = sum(1 for kw in keywords if kw in text_to_check)
            
            if len(keywords) > 0 and (overlap / len(keywords)) >= 0.5:
                # Source supports the claim
                source_type = src.get("source", "Unknown Source")
                matches.append(source_type)
                
                # Boost confidence based on source authority
                if "ArXiv" in source_type:
                    confidence += 0.25 # Academic papers get high weight
                elif "Wikipedia" in source_type:
                    confidence += 0.15 # Wiki gets moderate weight
                else:
                    confidence += 0.10
                    
        confidence = min(1.0, confidence)
        status = "UNVERIFIED"
        if confidence >= 0.7:
            status = "VERIFIED"
        elif confidence >= 0.5:
            status = "PARTIALLY_VERIFIED"
            
        return {
            "claim": claim,
            "confidence": round(confidence, 2),
            "status": status,
            "supporting_sources": list(set(matches))
        }

# Singleton
fact_verification_engine = FactVerificationEngine()
