# ZOHRA OS — Voice API Router & Management Gateway
import logging
import time
import os
import asyncio
import re
from urllib.parse import urlparse
from importlib.util import find_spec
from typing import Optional, Dict, Any
from pydantic import BaseModel

try:
    from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Response
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

if FASTAPI_AVAILABLE:
    from zohra.services.voice.voice_gateway import VoiceGatewayService
    from zohra.services.voice.audio_capture import AudioCaptureEngine
    from zohra.services.voice.voice_memory import VoiceMemoryEngine
    from zohra.services.voice.tts_connector import TTSConnector

    logger = logging.getLogger("zohra.api.voice")
    router = APIRouter(prefix="/api/v1/voice", tags=["Voice Division Services"])
    gateway = None
    gateway_lock = asyncio.Lock()
    preview_tts = None
    
    class VoiceSettingsPayload(BaseModel):
        username: str
        speaking_speed: float
        response_length_pref: str
        preferred_voice_id: str
        preferred_language: str

    @router.websocket("/stream")
    async def voice_stream_endpoint(websocket: WebSocket, session_id: Optional[str] = "default_voice_session"):
        """
        WebSocket endpoint streaming 16kHz Mono 16-bit PCM raw audio
        and receiving progressive synthesized responses.
        """
        origin = websocket.headers.get("origin")
        if (websocket.url.hostname not in {"127.0.0.1", "localhost", "::1"} or not websocket.client or
            websocket.client.host not in {"127.0.0.1", "::1"} or
            (origin and (urlparse(origin).netloc != websocket.headers.get("host") or
                urlparse(origin).scheme != ("https" if websocket.url.scheme == "wss" else "http"))) or
            not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id or "")):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        try:
            global gateway
            async with gateway_lock:
                if gateway is None:
                    gateway = await asyncio.to_thread(VoiceGatewayService)
            await gateway.process_voice_stream(websocket, session_id)
        except WebSocketDisconnect:
            logger.info(f"WebSocket client disconnected from voice stream: {session_id}")
        except Exception as e:
            logger.error(f"Voice WebSocket stream crashed: {e}")

    @router.get("/preview")
    async def preview_voice():
        """Speak the dashboard's fixed greeting with the configured female voice."""
        global preview_tts
        if preview_tts is None:
            preview_tts = await asyncio.to_thread(TTSConnector)
        if not preview_tts.available:
            raise HTTPException(status_code=503, detail="Female voice unavailable")
        try:
            audio = await asyncio.to_thread(
                preview_tts.synthesize, "Hello, I am Zohra. I am ready when you are.", "friendly"
            )
        except Exception as exc:
            logger.error("Voice preview failed: %s", exc)
            raise HTTPException(status_code=503, detail="Voice preview unavailable") from exc
        return Response(audio, media_type="audio/wav", headers={"Cache-Control": "no-store"})

    @router.get("/devices")
    async def get_audio_devices():
        """Lists all available input/output hardware audio devices."""
        try:
            engine = AudioCaptureEngine()
            devices = engine.device_manager.list_input_devices()
            return {"status": "success", "devices": devices}
        except Exception as e:
            logger.error(f"Failed to list audio devices: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/settings")
    async def update_voice_settings(settings: VoiceSettingsPayload):
        """Updates user-specific voice preferences in the database."""
        try:
            memory = VoiceMemoryEngine()
            memory.save_preferences(settings.username, settings.dict())
            return {"status": "success", "message": "Voice preferences updated."}
        except Exception as e:
            logger.error(f"Failed to update voice settings: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/diagnostics")
    async def run_voice_diagnostics():
        """Triggers a complete self-test of the voice components and returns a health report."""
        try:
            engine = AudioCaptureEngine()
            memory = VoiceMemoryEngine()
            
            # 1. Test hardware availability
            mic_available = engine.available
            default_mic = engine.device_manager.get_default_input_device()
            
            # 2. Test database connection
            db_status = "connected"
            try:
                memory._load_pronunciation_lexicon()
            except Exception:
                db_status = "disconnected"
                
            provider = os.getenv("VOICE_STT_PROVIDER", "local").lower()
            if gateway:
                stt_ready = bool(gateway.stt.local_model) or (
                    gateway.stt.provider == "cloud" and bool(gateway.stt.deepgram_api_key or gateway.stt.openai_api_key))
                stt_status = "ready" if stt_ready else "unavailable"
                tts_status = "ready" if gateway.tts.available else "unavailable"
            else:
                # Inspect availability without downloading models or starting audio engines.
                stt_installed = bool(find_spec("faster_whisper")) if provider == "local" else bool(
                    os.getenv("DEEPGRAM_API_KEY") or os.getenv("OPENAI_API_KEY")) if provider == "cloud" else False
                stt_status = "not_initialized" if stt_installed else "unavailable"
                if preview_tts is not None:
                    tts_status = "ready" if preview_tts.available else "unavailable"
                else:
                    tts_status = "not_initialized" if os.name == "nt" or find_spec("pyttsx3") else "unavailable"

            report = {
                "status": "healthy" if (mic_available and default_mic and db_status == "connected"
                                         and stt_status == tts_status == "ready") else "degraded",
                "timestamp": time.time(),
                "components": {
                    "audio_capture": "available" if mic_available and default_mic else "unavailable",
                    "database": db_status,
                    "speech_recognition": stt_status,
                    "speech_synthesis": tts_status,
                    "speech_voice": (gateway.tts.selected_voice if gateway else
                                     preview_tts.selected_voice if preview_tts else "not_initialized"),
                    "voice_gateway": "initialized" if gateway else "idle"
                },
                "hardware": {
                    "default_microphone": default_mic["name"] if default_mic else "None",
                    "input_channels": default_mic["max_input_channels"] if default_mic else 0
                }
            }
            return {"status": "success", "diagnostics": report}
        except Exception as e:
            logger.error(f"Diagnostics run failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))
else:
    router = None
