# ZOHRA OS — Voice Session & Authentication Models
from typing import Optional, Literal
from pydantic import BaseModel, Field
import uuid
import time

class VoiceSession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    enrolled_user_id: Optional[str] = None
    wake_word_triggered_at: float = Field(default_factory=time.time)
    transcript_final: Optional[str] = None
    auth_result: Optional[Literal["approved", "rejected", "not_required"]] = "not_required"
    interrupted: bool = False

class AuthResult(BaseModel):
    status: Literal["approved", "rejected"]
    confidence: float
    reason: str
