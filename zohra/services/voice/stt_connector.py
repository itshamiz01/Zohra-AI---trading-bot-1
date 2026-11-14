# ZOHRA OS — Speech-To-Text Connector (STT Router)
import logging
import asyncio
import os
import requests
import json
from typing import Optional
import numpy as np

from zohra.event_bus import event_bus

logger = logging.getLogger("zohra.voice.stt")

class STTResult:
    def __init__(self, text: str, confidence: float, is_partial: bool):
        self.text = text
        self.confidence = confidence
        self.is_partial = is_partial

class STTConnector:
    """
    Speech-To-Text Router supporting:
    - Cloud: Deepgram / OpenAI Whisper API
    - Local: faster-whisper (ONNX) offline fallback
    - Graceful failovers between modes
    """
    def suppress_noise(self, audio_data: bytes) -> bytes:
        """Lightweight real-time noise suppression / spectral gate."""
        if not audio_data:
            return audio_data
        import numpy as np
        samples = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
        # Suppress elements below dynamic noise threshold
        threshold = np.std(samples) * 0.1
        samples[np.abs(samples) < threshold] *= 0.15
        return samples.astype(np.int16).tobytes()

    def process_chunk(self, chunk: bytes) -> STTResult:
        """Transcribe a complete PCM segment; providers do not expose confidence."""
        return STTResult(self.transcribe(chunk), None, is_partial=False)

    async def stream_stt(self, audio_chunks, session_id: str):
        """Assemble a bounded utterance and transcribe it off the event loop."""
        audio = bytearray()
        async for chunk in audio_chunks:
            audio.extend(chunk)
            if len(audio) > 16000 * 2 * 60:
                raise ValueError("Voice utterances are limited to 60 seconds")
        text = await asyncio.to_thread(self.transcribe, bytes(audio)) if audio else ""
        if text:
            await event_bus.publish("voice.transcript.final", {
                "session_id": session_id, "text": text, "confidence": None,
            })
        return text
    def __init__(self, provider: str = "auto"):
        # Load settings from environment
        self.provider = os.getenv("VOICE_STT_PROVIDER", provider).lower()
        self.deepgram_api_key = os.getenv("DEEPGRAM_API_KEY")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        
        # Check if local faster-whisper is available
        self.local_model = None
        if self.provider == "local" or (self.provider == "auto" and not (self.groq_api_key or self.deepgram_api_key or self.openai_api_key)):
            self._init_local_whisper()
            
        logger.info(f"STT Connector initialized. Active Provider: {self.provider} (Groq: {bool(self.groq_api_key)}, OpenAI: {bool(self.openai_api_key)})")

    def _init_local_whisper(self):
        try:
            from faster_whisper import WhisperModel
            # Load small/base model locally for low latency
            model_size = os.getenv("LOCAL_WHISPER_MODEL", "base")
            logger.info(f"Loading local Whisper model ({model_size}) on CPU/GPU...")
            # Use GPU if CUDA is available
            device = "cuda" if os.getenv("CUDA_AVAILABLE") == "true" else "cpu"
            self.local_model = WhisperModel(model_size, device=device, compute_type="int8")
            logger.info("Local Whisper model loaded successfully.")
        except Exception as e:
            logger.warning(f"Local faster-whisper not available: {e}. Speech transcription is unavailable.")
            self.local_model = None

    def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> str:
        """Transcribes PCM audio byte data using the configured provider with fallbacks."""
        if not audio_data:
            return ""
        if len(audio_data) % 2 or not 8000 <= sample_rate <= 192000:
            raise ValueError("Expected mono 16-bit PCM with a valid sample rate")
        if sample_rate != 16000:
            samples = np.frombuffer(audio_data, dtype=np.int16)
            count = max(1, round(len(samples) * 16000 / sample_rate))
            audio_data = np.interp(np.arange(count) * sample_rate / 16000,
                                  np.arange(len(samples)), samples).astype(np.int16).tobytes()
        if self.provider in ("cloud", "auto"):
            if self.groq_api_key:
                text = self._transcribe_groq(audio_data)
                if text:
                    return text
            if self.deepgram_api_key:
                text = self._transcribe_deepgram(audio_data)
                if text:
                    return text
            if self.openai_api_key:
                text = self._transcribe_openai(audio_data)
                if text:
                    return text
            if self.provider == "cloud":
                logger.warning("Cloud STT requested but no API keys succeeded. Falling back to local.")
                
        return self._transcribe_local(audio_data)

    def _transcribe_groq(self, audio_data: bytes) -> str:
        """Fast cloud Whisper transcription using Groq API."""
        try:
            url = "https://api.groq.com/openai/v1/audio/transcriptions"
            headers = {"Authorization": f"Bearer {self.groq_api_key}"}
            wav_data = self._wrap_pcm_wav(audio_data)
            files = {
                "file": ("audio.wav", wav_data, "audio/wav"),
                "model": (None, "whisper-large-v3-turbo"),
                "prompt": (None, "Zohra trading voice companion in English, Hindi, Urdu, Hinglish, market, gold, XAUUSD, profit, buy, sell.")
            }
            response = requests.post(url, headers=headers, files=files, timeout=8.0)
            if response.status_code == 200:
                transcript = response.json().get("text", "").strip()
                logger.info(f"Groq Whisper transcription success: '{transcript}'")
                return transcript
            else:
                logger.error(f"Groq Whisper STT API error {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"Groq Whisper STT connection failed: {e}")
        return ""

    def _transcribe_deepgram(self, audio_data: bytes) -> str:
        try:
            url = "https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true"
            headers = {
                "Authorization": f"Token {self.deepgram_api_key}",
                "Content-Type": "audio/wav"
            }
            # Add simple WAV headers to raw PCM so Deepgram knows the format
            wav_data = self._wrap_pcm_wav(audio_data)
            
            response = requests.post(url, headers=headers, data=wav_data, timeout=5.0)
            if response.status_code == 200:
                res_json = response.json()
                transcript = res_json.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0].get("transcript", "")
                return transcript
            else:
                logger.error(f"Deepgram STT API error {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"Deepgram STT connection failed: {e}. Falling back to local.")
            
        return self._transcribe_local(audio_data)

    def _transcribe_openai(self, audio_data: bytes) -> str:
        try:
            url = "https://api.openai.com/v1/audio/transcriptions"
            headers = {"Authorization": f"Bearer {self.openai_api_key}"}
            wav_data = self._wrap_pcm_wav(audio_data)
            
            # Send as multipart form file
            files = {
                "file": ("audio.wav", wav_data, "audio/wav"),
                "model": (None, "whisper-1")
            }
            response = requests.post(url, headers=headers, files=files, timeout=8.0)
            if response.status_code == 200:
                return response.json().get("text", "")
            else:
                logger.error(f"OpenAI STT API error {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"OpenAI STT connection failed: {e}. Falling back to local.")
            
        return self._transcribe_local(audio_data)

    def _transcribe_local(self, audio_data: bytes) -> str:
        if self.local_model:
            try:
                # Convert raw PCM bytes back to float32 numpy array for faster-whisper
                audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
                segments, info = self.local_model.transcribe(audio_np, beam_size=5)
                transcript = " ".join([segment.text for segment in segments])
                return transcript
            except Exception as e:
                logger.error(f"Local Whisper transcription failed: {e}")
                
        logger.info("Speech transcription is unavailable because no local model is configured.")
        return ""

    def _wrap_pcm_wav(self, pcm_data: bytes, sample_rate: int = 16000) -> bytes:
        """Wraps raw 16kHz mono 16-bit PCM bytes into a standard WAV container."""
        import struct
        num_samples = len(pcm_data) // 2
        num_channels = 1
        bytes_per_sample = 2
        
        # WAV Header fields
        riff_tag = b'RIFF'
        file_size = 36 + len(pcm_data)
        wave_tag = b'WAVE'
        fmt_tag = b'fmt '
        fmt_size = 16
        audio_format = 1 # PCM
        byte_rate = sample_rate * num_channels * bytes_per_sample
        block_align = num_channels * bytes_per_sample
        bits_per_sample = 8 * bytes_per_sample
        data_tag = b'data'
        data_size = len(pcm_data)
        
        header = struct.pack(
            '<4sI4s4sIHHIIHH4sI',
            riff_tag, file_size, wave_tag, fmt_tag, fmt_size,
            audio_format, num_channels, sample_rate, byte_rate,
            block_align, bits_per_sample, data_tag, data_size
        )
        return header + pcm_data
