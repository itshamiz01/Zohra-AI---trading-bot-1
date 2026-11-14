# ZOHRA OS — Voice Gateway & Conversational Brain
import logging
import asyncio
import json
import re
from contextlib import suppress
from typing import Dict, Any, Optional, List
from zohra.services.voice.stt_connector import STTConnector
from zohra.services.voice.tts_connector import TTSConnector, EMOTION_MAP
from zohra.services.voice.speaker_id import SpeakerIdentifier
from zohra.services.voice.voice_memory import VoiceMemoryEngine
from zohra.services.voice.portrait_commands import portrait_command

logger = logging.getLogger("zohra.voice.gateway")

# Safety Redaction Regex Patterns
CREDENTIAL_PATTERNS = [
    re.compile(r'sk-[a-zA-Z0-9]{32,}', re.IGNORECASE),     # OpenAI / generic keys
    re.compile(r'gsk_[a-zA-Z0-9]{32,}', re.IGNORECASE),    # Groq keys
    re.compile(r'password\s*:\s*\S+', re.IGNORECASE),      # Passwords
    re.compile(r'api_key\s*:\s*\S+', re.IGNORECASE),       # API keys
    re.compile(r'secret\s*:\s*\S+', re.IGNORECASE),        # Secrets
]

class VoiceGatewayService:
    """
    Manages active voice sessions over WebSockets.
    Implements the Conversational Brain & Personality:
    - Voice State Machine (IDLE, LISTENING, THINKING, SPEAKING)
    - Speaker Identification (Owner verification vs Guest mode)
    - Voice Memory & Pronunciation Engine (XAUUSD -> Gold Spot Dollar, etc.)
    - Emotional Voice Engine (Neutral, Excited, Concerned, Calm, Professional)
    - Safety Redaction (Masks API keys, passwords, and thoughts)
    - Progressive Sentence-by-Sentence TTS Streaming
    """
    def __init__(self):
        self.stt = STTConnector()
        self.tts = TTSConnector()
        self.speaker_id = SpeakerIdentifier()
        self.voice_memory = VoiceMemoryEngine()
        logger.info("Voice Gateway Service & Conversational Brain initialized.")

    async def process_voice_stream(self, websocket, session_id: str):
        """
        Main session loop handling incoming client audio stream,
        control messages, and routing responses with interruption support.
        """
        logger.info(f"Active voice session connection started: {session_id}")
        audio_buffer = bytearray()
        
        # Track the active response task so we can cancel it on user interruption
        active_response_task: Optional[asyncio.Task] = None
        
        # Broadcast gateway online
        await self._send_status(websocket, "VOICE_GATEWAY_ONLINE")
        
        try:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                
                # ─── 1. Handle Binary Audio Input ───────────────────
                if message.get("bytes") is not None:
                    pcm_chunk = message["bytes"]
                    audio_buffer.extend(pcm_chunk)
                    if len(audio_buffer) > 16000 * 2 * 60:
                        audio_buffer.clear()
                        await websocket.send_text(json.dumps({"type": "error", "content": "Utterances are limited to 60 seconds."}))
                        await websocket.close(code=1009)
                        break
                    
                # ─── 2. Handle Control Signals (JSON) ───────────────
                elif message.get("text") is not None:
                    try:
                        data = json.loads(message["text"])
                        if not isinstance(data, dict):
                            continue
                        event_type = data.get("type")
                        
                        if event_type in {"speech_started", "portrait_hidden"}:
                            logger.info(f"User speech start detected for session: {session_id}")
                            # INTERRUPT TRIGGER: If the bot is currently speaking/reasoning, interrupt it!
                            if active_response_task and not active_response_task.done():
                                logger.info(f"⚡ User interrupted Zohra. Cancelling active response task...")
                                active_response_task.cancel()
                                with suppress(asyncio.CancelledError):
                                    await active_response_task
                                # Notify client to stop playing any active audio immediately
                                await websocket.send_text(json.dumps({
                                    "type": "interrupt",
                                    "content": "STOP_PLAYBACK"
                                }))
                            if event_type == "portrait_hidden":
                                audio_buffer.clear()
                            await self._send_status(websocket,
                                "LISTENING" if event_type == "portrait_hidden" else "RECORDING")
                            
                        elif event_type == "speech_stopped":
                            logger.info(f"Speech end detected. Processing segment for session: {session_id}")
                            
                            # Retrieve the accumulated audio
                            raw_audio = bytes(audio_buffer)
                            audio_buffer.clear()
                            
                            if len(raw_audio) == 0:
                                await websocket.send_text(json.dumps({
                                    "type": "error",
                                    "content": "EMPTY_AUDIO_BUFFER"
                                }))
                                continue
                                
                            if active_response_task and not active_response_task.done():
                                active_response_task.cancel()
                                with suppress(asyncio.CancelledError):
                                    await active_response_task
                            # Start processing the response in a cancellable task
                            active_response_task = asyncio.create_task(
                                self._generate_and_stream_response(websocket, session_id, raw_audio,
                                    control_only=data.get("control_only") is True)
                            )
                            
                        elif event_type == "text_input":
                            text = data.get("content")
                            if not isinstance(text, str) or not text.strip() or len(text) > 4000:
                                await websocket.send_text(json.dumps({"type": "error", "content": "Enter a message of 1 to 4000 characters."}))
                                continue
                            audio_buffer.clear()
                            if active_response_task and not active_response_task.done():
                                active_response_task.cancel()
                                with suppress(asyncio.CancelledError):
                                    await active_response_task
                            await websocket.send_text(json.dumps({"type": "interrupt", "content": "STOP_PLAYBACK"}))
                            active_response_task = asyncio.create_task(
                                self._generate_and_stream_response(websocket, session_id, b"", text_input=text.strip()))

                        elif event_type == "history":
                            from zohra.services.chat.assistant_store import assistant_store
                            history = await asyncio.to_thread(assistant_store.history, session_id, True)
                            await websocket.send_text(json.dumps({"type": "history", "messages": history}))

                        elif event_type == "ping":
                            await websocket.send_text(json.dumps({"type": "pong"}))
                            
                    except json.JSONDecodeError:
                        logger.error("Failed to parse incoming WebSocket text frame as JSON.")
                    except Exception as err:
                        logger.error(f"Error handling control event: {err}")
                        
        except Exception as e:
            logger.error(f"Voice session socket disconnected or errored: {e}")
        finally:
            # Cleanup any running tasks
            if active_response_task and not active_response_task.done():
                active_response_task.cancel()
                with suppress(asyncio.CancelledError):
                    await active_response_task
            logger.info(f"Voice session closed: {session_id}")

    async def _send_status(self, websocket, status: str):
        """Helper to send a status update to the client."""
        try:
            await websocket.send_text(json.dumps({
                "type": "status",
                "content": status
            }))
        except Exception as e:
            logger.error(f"Failed to send status {status}: {e}")

    async def _generate_and_stream_response(self, websocket, session_id: str, raw_audio: bytes,
                                            control_only: bool = False, text_input: Optional[str] = None):
        """Processes the voice query: Speaker ID -> STT -> Brain -> Progressive TTS."""
        try:
            from zohra.services.voice.interrupt_detector import INTERRUPT_STORE
            INTERRUPT_STORE[f"interrupt_flag:{session_id}"] = "0"

            # 1. Speaker Identification
            await self._send_status(websocket, "IDENTIFYING_SPEAKER")
            username, confidence, role = (("Guest", 0.0, "guest") if text_input is not None else
                                         await asyncio.to_thread(self.speaker_id.identify_speaker, raw_audio))
            
            await websocket.send_text(json.dumps({
                "type": "speaker",
                "name": username,
                "confidence": confidence,
                "role": role
            }))
            
            # 2. Speech-To-Text (STT)
            await self._send_status(websocket, "TRANSCRIBING")
            transcript = text_input if text_input is not None else await asyncio.to_thread(self.stt.transcribe, raw_audio)
            logger.info(f"STT Transcript: '{transcript}'")
            
            if not transcript or transcript.strip() == "":
                await websocket.send_text(json.dumps({"type": "error", "content":
                    "No speech was transcribed. Check the speech-recognition provider and microphone."}))
                await self._send_status(websocket, "LISTENING")
                return

            command = portrait_command(transcript)
            if command or control_only:
                await websocket.send_text(json.dumps({"type": "transcript", "content": transcript}))
                if command:
                    await websocket.send_text(json.dumps({"type": "interrupt", "content": "STOP_PLAYBACK"}))
                    await websocket.send_text(json.dumps({"type": "portrait", "action": command}))
                await self._send_status(websocket, "LISTENING")
                return

            await websocket.send_text(json.dumps({
                "type": "transcript",
                "content": transcript
            }))
            
            # 3. Feed into ZohraBrain reasoning loop with Speaker context
            await self._send_status(websocket, "THINKING")
            
            from zohra.services.chat.assistant_orchestrator import voice_events
            
            # Progressive Sentence Synthesis variables
            sentence_buffer = ""
            sentence_end_pattern = re.compile(r'(?<=[.!?\u0964])\s+')
            
            async for event in voice_events(session_id, transcript):
                # Check for interruption
                if INTERRUPT_STORE.get(f"interrupt_flag:{session_id}") == "1":
                    logger.info("Interrupt active. Stopping token processing.")
                    break

                if event["type"] == "token":
                    token = self._refine_and_sanitize(event["content"])
                    sentence_buffer += token
                    
                    # Yield token to client UI
                    await websocket.send_text(json.dumps({
                        "type": "token",
                        "content": token
                    }))
                    
                    # Check for sentence boundaries to trigger progressive synthesis
                    sentences = sentence_end_pattern.split(sentence_buffer)
                    if len(sentences) > 1:
                        # Process the completed sentence
                        sentence_buffer = sentences[-1]
                        for completed_sentence in sentences[:-1]:
                            completed_sentence = completed_sentence.strip()
                            if not completed_sentence:
                                continue
                            # Apply safety redaction & pronunciation substitution
                            refined_sentence = self._refine_and_sanitize(completed_sentence)
                            emotion = self._classify_emotion(refined_sentence)
                            await self._synthesize_and_stream_chunk(websocket, refined_sentence, emotion, session_id)
                            
                elif event["type"] == "thought":
                    continue
                elif event["type"] == "tool":
                    await websocket.send_text(json.dumps({
                        "type": "tool",
                        "name": event["name"],
                        "args": event.get("args", {})
                    }))
                elif event["type"] == "error":
                    await websocket.send_text(json.dumps({"type": "error", "content": event["content"]}))
                elif event["type"] == "sources":
                    await websocket.send_text(json.dumps(event))
                elif event["type"] == "assistant_result":
                    await websocket.send_text(json.dumps(event))
                elif event["type"] == "acknowledgement":
                    content = self._refine_and_sanitize(event["content"])
                    await websocket.send_text(json.dumps({"type": "acknowledgement", "content": content}))
                    await self._synthesize_and_stream_chunk(websocket, content,
                        self._classify_emotion(content), session_id)

            # Synthesize any remaining text in the buffer
            if sentence_buffer.strip() and INTERRUPT_STORE.get(f"interrupt_flag:{session_id}") != "1":
                refined_sentence = self._refine_and_sanitize(sentence_buffer.strip())
                emotion = self._classify_emotion(refined_sentence)
                await self._synthesize_and_stream_chunk(websocket, refined_sentence, emotion, session_id)
                
            await websocket.send_text(json.dumps({"type": "response_done"}))
            # Reset status to listening
            await self._send_status(websocket, "LISTENING")
            
        except asyncio.CancelledError:
            logger.info("Response generation task cancelled due to user interruption.")
            try:
                await self._send_status(websocket, "LISTENING")
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Error in response generation pipeline: {e}")
            try:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "content": f"PIPELINE_ERROR: {str(e)}"
                }))
            except Exception:
                pass

    def _refine_and_sanitize(self, text: str) -> str:
        """Applies safety redaction and pronunciation substitutions."""
        # 1. Safety Redaction (Mask API Keys and Passwords)
        for pattern in CREDENTIAL_PATTERNS:
            text = pattern.sub("[secret redacted]", text)
            
        # 2. Pronunciation Substitutions (XAUUSD -> Gold Spot Dollar, etc.)
        text = self.voice_memory.apply_pronunciation(text)
        
        return text

    def _classify_emotion(self, text: str) -> str:
        """Heuristic-based emotion classifier for vocal tone adaptation."""
        text_lower = text.lower()
        
        # Celebratory / Excited
        if any(w in text_lower for w in ["congratulations", "profit", "take profit", "great news", "excellent", "success"]):
            return "excited"
            
        # Concerned / Serious
        if any(w in text_lower for w in ["warning", "drawdown", "margin call", "danger", "error", "critical", "vetoed"]):
            return "concerned"
            
        # Calm / Reassuring
        if any(w in text_lower for w in ["halted", "paused", "safe", "stable", "calm", "secured"]):
            return "calm"
            
        # Professional / Analytical (Default)
        return "professional"

    async def _synthesize_and_stream_chunk(self, websocket, text: str, emotion: str, session_id: str):
        """Synthesizes a sentence chunk and streams the binary audio immediately, checking for interrupts."""
        try:
            from zohra.services.voice.interrupt_detector import set_tts_playing, INTERRUPT_STORE
            # Check if interrupted before speaking
            if INTERRUPT_STORE.get(f"interrupt_flag:{session_id}") == "1":
                logger.info("Playback interrupted before start.")
                return

            set_tts_playing(session_id, True)
            await self._send_status(websocket, "SPEAKING")
            logger.info(f"Progressive TTS synthesis chunk: '{text}' (Emotion: {emotion})")
            speech = re.sub(r"\[([^\]]+)\]\(https?://[^)]+\)", r"\1", text)
            speech = re.sub(r"(?m)^\s*(?:[-*#]+|\d+[.)])\s+", "", speech)
            speech = re.sub(r"[*`_]+", "", speech)
            speech = re.sub(r"DISPLAY\\[^\s.]+", "the selected monitor", speech)
            audio_chunk = await asyncio.to_thread(self.tts.synthesize, speech, emotion)
            
            # Double check interrupt flag before writing to socket
            if INTERRUPT_STORE.get(f"interrupt_flag:{session_id}") == "1":
                logger.info("Playback interrupted during synthesis.")
                set_tts_playing(session_id, False)
                return

            await websocket.send_bytes(audio_chunk)
            set_tts_playing(session_id, False)
        except Exception as e:
            logger.error(f"Failed to synthesize progressive chunk: {e}")
            try:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "content": "Voice output is unavailable on this device."
                }))
            except Exception:
                pass
            from zohra.services.voice.interrupt_detector import set_tts_playing
            set_tts_playing(session_id, False)

            
    # Keep session state broadcast for UI synchronization
    async def get_voice_personality_status(self) -> Dict[str, Any]:
        return {
            "identity": "Zohra Core",
            "accent": "US/Neutral",
            "emotions_supported": list(EMOTION_MAP.keys()),
            "pronunciation_count": len(self.voice_memory.pronunciation_cache)
        }
