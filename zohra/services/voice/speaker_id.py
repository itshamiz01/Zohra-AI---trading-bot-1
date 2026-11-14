# ZOHRA OS — Speaker Identification & Voice Signature Engine
import json
import logging
import os
import numpy as np
from pathlib import Path
from typing import Dict, Any, Tuple

logger = logging.getLogger("zohra.voice.speaker")

class SpeakerIdentifier:
    """
    Extracts acoustic voice signatures through a configured verifier
    and verifies speaker profiles for security and personalization.
    """
    def __init__(self):
        self.enrolled_speakers = self._load_profiles()
        self.feature_extractor = None
        logger.info(f"Speaker Identification Engine loaded. Enrolled: {list(self.enrolled_speakers.keys())}")

    @staticmethod
    def _load_profiles() -> Dict[str, Dict[str, Any]]:
        """Load operator-provisioned embeddings only; never ship a fake owner."""
        location = os.getenv("ZOHRA_VOICE_PROFILES_PATH", "").strip()
        if not location:
            return {}
        try:
            raw = json.loads(Path(location).read_text(encoding="utf-8"))
            profiles = {}
            for name, profile in raw.items():
                signature = np.asarray(profile.get("signature", []), dtype=np.float32)
                if signature.size < 32 or not np.isfinite(signature).all():
                    logger.warning("Ignoring invalid voice profile for %s", name)
                    continue
                profiles[name] = {**profile, "signature": signature, "role": "owner"}
            return profiles
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("Could not load voice profiles: %s", exc)
            return {}

    def identify_speaker(self, audio_data: bytes) -> Tuple[str, float, str]:
        """
        Analyzes the first few seconds of audio, extracts the voice signature,
        and matches it against enrolled profiles using Cosine Similarity.
        Returns: Tuple[username, confidence_score, role]
        """
        if len(audio_data) < 3200 or self.feature_extractor is None:
            return "Unknown", 0.0, "guest"

        try:
            extracted_signature = np.asarray(self.feature_extractor(audio_data), dtype=np.float32)
        except Exception as exc:
            logger.warning("Voice feature extraction failed: %s", exc)
            return "Unknown", 0.0, "guest"
        if extracted_signature.size == 0 or not np.isfinite(extracted_signature).all():
            return "Unknown", 0.0, "guest"
        
        # Normalize signature
        norm = np.linalg.norm(extracted_signature)
        if norm == 0:
            return "Unknown", 0.0, "guest"
        sim_norm = extracted_signature / norm
        
        best_match = "Unknown"
        best_score = 0.0
        role = "guest"
        
        for name, profile in self.enrolled_speakers.items():
            stored_sig = profile["signature"]
            stored_norm = stored_sig / np.linalg.norm(stored_sig)
            if stored_norm.shape != sim_norm.shape:
                continue
            
            # Calculate Cosine Similarity
            similarity = float(np.dot(sim_norm, stored_norm))
            
            if similarity > best_score:
                best_score = similarity
                if similarity >= 0.82: # Confidence threshold
                    best_match = name
                    role = profile["role"]
                    
        logger.info(f"Speaker ID verification: Match='{best_match}', Confidence={best_score:.4f}, Role='{role}'")
        return best_match, best_score, role

    def passes_liveness_check(self, audio_sample: bytes) -> bool:
        """
        Liveness check: mitigates simple recorded-audio replay attacks.
        Checks for artificial replay spectral characteristics.
        """
        logger.warning("Voice liveness verification is unavailable; denying sensitive voice action.")
        return False

    def voice_authenticate(self, audio_sample: bytes, claimed_user_id: str, required_confidence: float = 0.92) -> Any:
        """
        Voice authentication check to gate OS and trading commands.
        Performs high-confidence embedding validation and liveness audit checks.
        """
        from zohra.services.voice.models import AuthResult
        
        # Resolve signature match
        name, similarity, role = self.identify_speaker(audio_sample)
        
        # Check claimed user
        if name.lower() != claimed_user_id.lower():
            logger.warning(f"Voice auth failed: claimed user '{claimed_user_id}' does not match verified name '{name}'")
            return AuthResult(status="rejected", confidence=similarity, reason="User identity mismatch")

        if similarity < required_confidence:
            logger.warning(f"Voice auth failed: similarity {similarity:.4f} is below required threshold {required_confidence:.4f}")
            return AuthResult(status="rejected", confidence=similarity, reason="Low similarity confidence")

        if not self.passes_liveness_check(audio_sample):
            return AuthResult(status="rejected", confidence=similarity, reason="Liveness check failed")

        logger.info(f"Voice auth approved for user '{claimed_user_id}' with similarity {similarity:.4f}")
        return AuthResult(status="approved", confidence=similarity, reason="Authentication passed")
