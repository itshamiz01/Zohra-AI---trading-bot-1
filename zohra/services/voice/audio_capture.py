# ZOHRA OS — Audio Capture & Pre-Processing Engine
import logging
import queue
import threading
import time
import json
from typing import List, Dict, Any, Optional
import numpy as np

logger = logging.getLogger("zohra.voice.capture")

class AudioDeviceManager:
    """
    Manages audio input devices, handles hot-swapping,
    queries capabilities, and switches default devices dynamically.
    """
    def __init__(self, sd_module=None):
        self.sd = sd_module
        
    def list_input_devices(self) -> List[Dict[str, Any]]:
        if not self.sd:
            return []
        
        try:
            devices = self.sd.query_devices()
            input_devices = []
            for idx, dev in enumerate(devices):
                if dev.get("max_input_channels", 0) > 0:
                    input_devices.append({
                        "id": idx,
                        "name": dev.get("name"),
                        "max_input_channels": dev.get("max_input_channels"),
                        "default_sample_rate": dev.get("default_samplerate"),
                        "is_default": idx == self.sd.default.device[0]
                    })
            return input_devices
        except Exception as e:
            logger.error(f"Failed to query audio input devices: {e}")
            return []

    def get_default_input_device(self) -> Optional[Dict[str, Any]]:
        devices = self.list_input_devices()
        for dev in devices:
            if dev.get("is_default"):
                return dev
        return devices[0] if devices else None


class AudioPreProcessor:
    """
    Modular DSP pre-processing chain:
    - Downsampling/Sample Rate Conversion (from input rate to 16kHz)
    - Noise gating / suppression
    - Automatic Gain Control (AGC) / Normalization
    """
    def __init__(self, input_rate: int, target_rate: int = 16000):
        self.input_rate = input_rate
        self.target_rate = target_rate
        self.ratio = target_rate / input_rate
        
    def process(self, frame: np.ndarray) -> np.ndarray:
        """Applies downsampling, noise gate, and gain normalization."""
        # 1. Convert to mono if multi-channel
        if frame.ndim > 1 and frame.shape[1] > 1:
            frame = np.mean(frame, axis=1)
        else:
            frame = frame.flatten()

        # 2. Downsample to 16kHz
        if self.input_rate != self.target_rate:
            frame = self._resample(frame)

        # 3. Noise Gate / Simple Noise Suppression
        frame = self._apply_noise_gate(frame)

        # 4. Automatic Gain Control (AGC)
        frame = self._apply_agc(frame)
        
        return frame

    def _resample(self, frame: np.ndarray) -> np.ndarray:
        """Linear interpolation resampling (extremely fast, low latency)."""
        duration = len(frame) / self.input_rate
        num_target_samples = int(duration * self.target_rate)
        if num_target_samples == 0:
            return np.array([], dtype=np.float32)
            
        src_indices = np.linspace(0, len(frame) - 1, num_target_samples)
        return np.interp(src_indices, np.arange(len(frame)), frame).astype(np.float32)

    def _apply_noise_gate(self, frame: np.ndarray, threshold: float = 0.02) -> np.ndarray:
        """Applies a soft noise gate to suppress background hiss/noise."""
        rms = np.sqrt(np.mean(frame**2)) if len(frame) > 0 else 0
        if rms < threshold:
            # Attenuate signal below threshold
            return frame * 0.1
        return frame

    def _apply_agc(self, frame: np.ndarray, target_rms: float = 0.15) -> np.ndarray:
        """Dynamic range normalization to keep speech levels consistent."""
        rms = np.sqrt(np.mean(frame**2)) if len(frame) > 0 else 0
        if rms < 0.001:
            return frame
        gain = target_rms / rms
        # Limit max gain to prevent amplifying silence/noise
        gain = min(gain, 5.0)
        normalized = frame * gain
        # Clip to prevent digital distortion
        return np.clip(normalized, -1.0, 1.0)


class AudioCaptureEngine:
    """
    Captures audio continuously from the hardware, downsamples and filters,
    and runs a lightweight Energy + VAD state machine locally.
    """
    def __init__(self, sample_rate: int = 16000, block_size: int = 800):
        self.target_rate = sample_rate
        self.block_size = block_size
        self.audio_queue = queue.Queue()
        self.running = False
        self.stream = None
        self.capture_thread = None
        
        # Initialize Device Manager
        try:
            import sounddevice as sd
            self.sd = sd
            self.available = True
            logger.info("sounddevice library successfully loaded.")
        except ImportError:
            self.sd = None
            self.available = False
            logger.warning("sounddevice not installed; local microphone capture is unavailable.")
            
        self.device_manager = AudioDeviceManager(self.sd)
        self.processor = None

        # VAD state parameters
        self.speaking = False
        self.silence_threshold = 0.015
        self.silence_duration_limit = 1.2 # seconds of silence before stopping
        self.last_speech_time = time.time()
        self.speech_buffer = bytearray()
        
    def start(self) -> bool:
        if self.running:
            return True
            
        self.running = True
        self.audio_queue.queue.clear()
        self.speech_buffer.clear()
        
        if not self.available or self.sd is None:
            self.running = False
            logger.info("Microphone unavailable; capture was not started.")
            return False

        try:
            default_dev = self.device_manager.get_default_input_device()
            if not default_dev:
                raise Exception("No input audio devices found.")
            
            input_rate = int(default_dev["default_sample_rate"])
            logger.info(f"Connecting to default microphone: {default_dev['name']} at {input_rate}Hz")
            
            self.processor = AudioPreProcessor(input_rate, self.target_rate)
            
            # Using 100ms blocks for input stream stability
            stream_block_size = int(input_rate * 0.05) 
            
            self.stream = self.sd.InputStream(
                device=default_dev["id"],
                samplerate=input_rate,
                channels=1,
                blocksize=stream_block_size,
                callback=self._audio_callback,
                dtype='float32'
            )
            self.stream.start()
            logger.info("Audio capture stream started successfully.")
            return True
        except Exception as e:
            self.running = False
            self.stream = None
            logger.error(f"Hardware microphone initialization failed: {e}")
            return False

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            logger.warning(f"Audio capture callback status: {status}")
            
        if self.processor:
            # Process block through DSP chain
            clean_frame = self.processor.process(indata)
            
            # Convert float32 array (-1.0 to 1.0) to 16-bit PCM bytes
            pcm_bytes = (clean_frame * 32767).astype(np.int16).tobytes()
            self.audio_queue.put(pcm_bytes)
            
            # Perform VAD Analysis
            self._analyze_vad(clean_frame, pcm_bytes)

    def _analyze_vad(self, frame: np.ndarray, pcm_bytes: bytes):
        """Lightweight Energy-Based Voice Activity Detection state machine."""
        rms = np.sqrt(np.mean(frame**2)) if len(frame) > 0 else 0
        now = time.time()
        
        if rms > self.silence_threshold:
            self.last_speech_time = now
            if not self.speaking:
                self.speaking = True
                logger.info("🎙️ Speech START detected.")
                
            if self.speaking:
                self.speech_buffer.extend(pcm_bytes)
        else:
            if self.speaking:
                self.speech_buffer.extend(pcm_bytes)
                # Check if silence duration limit exceeded
                if now - self.last_speech_time > self.silence_duration_limit:
                    self.speaking = False
                    logger.info(f"🎙️ Speech STOP detected. Buffered {len(self.speech_buffer)} bytes.")
                    # Trigger speech end event (optional callback hook)

    def read_chunk(self, block: bool = True, timeout: float = 1.0) -> bytes:
        try:
            return self.audio_queue.get(block=block, timeout=timeout)
        except queue.Empty:
            return b""

    def get_speech_buffer(self) -> bytes:
        buf = bytes(self.speech_buffer)
        self.speech_buffer.clear()
        return buf

    def stop(self):
        self.running = False
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception as e:
                logger.error(f"Error closing audio input stream: {e}")
            self.stream = None
            
        if self.capture_thread:
            self.capture_thread.join(timeout=1.0)
            self.capture_thread = None
            
        logger.info("Audio capture engine stopped.")

# Alias for backward compatibility
AudioCaptureService = AudioCaptureEngine
