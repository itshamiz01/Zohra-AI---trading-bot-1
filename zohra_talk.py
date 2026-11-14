"""
══════════════════════════════════════════════════════════════════════════════
  ✦ ZOHRA AI — REAL-TIME TWO-WAY VOICE COMPANION (JARVIS ARCHITECTURE) ✦
  - Real-time Microphone Voice Input with Dynamic Adaptive VAD & Auto-Calibration
  - Fast Speech-To-Text via Cloud Whisper Turbo (Groq) with Multilingual Prompt
  - Intelligence powered by OpenRouter (openai/gpt-4o-mini)
  - Studio-grade Multilingual Human Neural TTS (Microsoft Neural Voices)
  - Speaks English, Hindi, Urdu, Hinglish, and 40+ languages with native clarity
══════════════════════════════════════════════════════════════════════════════
"""
import asyncio
import collections
import os
import sys
import threading
import time
import tempfile
import numpy as np

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from dotenv import load_dotenv

load_dotenv()

import sounddevice as sd
import pygame
import edge_tts

from zohra.services.chat.assistant_brain import assistant_brain
from zohra.services.voice.stt_connector import STTConnector
from zohra.services.voice.tts_connector import TTSConnector

# ANSI terminal colors
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
MAGENTA = "\033[95m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

# Supported High-Quality Voices
VOICE_CATALOG = {
    "ava": ("en-US-AvaMultilingualNeural", "Ava (Premier Multilingual Studio Female - Speaks English, Hindi, Urdu, 40+ langs)"),
    "emma": ("en-US-EmmaMultilingualNeural", "Emma (Expressive Multilingual Female - Clear, natural intonation)"),
    "swara": ("hi-IN-SwaraNeural", "Swara (Native Hindi Female - Pure Indian Hindi cadence)"),
    "uzma": ("ur-PK-UzmaNeural", "Uzma (Native Urdu Female - Authentic Pakistani Urdu intonation)"),
    "neerja": ("en-IN-NeerjaExpressiveNeural", "Neerja (Indian English Expressive Female)"),
    "brian": ("en-US-BrianMultilingualNeural", "Brian (Multilingual Studio Male - Deep, natural tone)"),
}


class ZohraLiveVoiceCompanion:
    def __init__(self):
        self.stt = STTConnector()
        self.tts = TTSConnector()
        self.session_id = f"zohra_voice_live_{os.getpid()}"

        # Default Voice: Ava Multilingual Neural (World-class multilingual clarity)
        env_voice = os.getenv("ZOHRA_TTS_VOICE", "en-US-AvaMultilingualNeural")
        self.selected_voice = env_voice
        self.voice_enabled = True

        # State flags
        self.is_speaking = False
        self.is_listening = True
        self.is_processing = False
        self.running = True
        self.interrupted = False

        # Barge-in (interruption) configuration
        self.barge_in_enabled = True
        self._barge_in_chunks = 0
        self.current_playing_file = None
        self._current_conv_task = None

        # Audio capture settings
        self.sample_rate = 16000
        self.block_size = 800  # 50ms blocks at 16kHz
        self.input_device = None

        # Adaptive Noise & VAD settings
        self.noise_floor = 40.0
        self.vad_threshold = float(os.getenv("VOICE_VAD_THRESHOLD", "140"))
        self.silence_limit_seconds = 0.65  # Snappy, human conversational turnaround
        self.ambient_tracking_enabled = True
        self.is_calibrating = False

        # Pre-speech circular buffer (300ms rolling window so start of words isn't clipped)
        self._pre_buffer = collections.deque(maxlen=6)
        self._speech_buffer = []
        self._silent_chunks = 0
        self._is_recording_utterance = False
        self._speech_start_time = 0.0
        self._main_loop = None

        # Init pygame mixer for crystal clear audio playback
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=24000)
        except Exception as e:
            print(f"{YELLOW}Audio playback warning: {e}{RESET}")

    def stop_speaking(self):
        """Immediately halts active speech synthesis and audio playback for instant barge-in."""
        self.interrupted = True
        self.is_speaking = False
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()
        except Exception:
            pass

        if self.current_playing_file and os.path.exists(self.current_playing_file):
            try:
                os.remove(self.current_playing_file)
            except Exception:
                pass
            self.current_playing_file = None

    def calibrate_mic(self, duration_sec: float = 0.8):
        """Measures ambient room noise to automatically calibrate VAD threshold."""
        print(f"{YELLOW}⏳ Calibrating microphone for ambient room noise... (please stay quiet){RESET}")
        calibration_rms = []

        def cal_callback(indata, frames, time_info, status):
            samples = np.frombuffer(indata, dtype=np.int16).astype(np.float32)
            rms = float(np.sqrt(np.mean(samples**2)))
            calibration_rms.append(rms)

        try:
            stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                callback=cal_callback,
                blocksize=self.block_size,
                device=self.input_device,
            )
            with stream:
                time.sleep(duration_sec)

            if calibration_rms:
                self.noise_floor = float(np.mean(calibration_rms))
                # Set threshold adaptively: ambient + 45, bounded between 90 and 350
                calculated = max(self.noise_floor * 1.8, self.noise_floor + 45.0)
                self.vad_threshold = float(max(90.0, min(350.0, calculated)))
                print(f"{GREEN}✓ Calibration Complete! Ambient Noise: {self.noise_floor:.1f} RMS | Sensitivity Trigger: {self.vad_threshold:.1f} RMS{RESET}")
            else:
                self.vad_threshold = 140.0
        except Exception as e:
            print(f"{YELLOW}Calibration warning: {e}. Using default threshold 140.0{RESET}")
            self.vad_threshold = 140.0

    def speak(self, text: str, blocking: bool = True):
        """Speaks out loud through computer speakers using Edge Multilingual Neural Voice with interruptibility."""
        if not self.voice_enabled or not text.strip() or self.interrupted:
            return

        self.is_speaking = True
        temp_file = os.path.join(tempfile.gettempdir(), f"zohra_speech_{int(time.time()*1000)}.mp3")
        self.current_playing_file = temp_file

        try:
            async def _synthesize():
                comm = edge_tts.Communicate(text, self.selected_voice)
                await comm.save(temp_file)

            asyncio.run(_synthesize())

            if self.interrupted or not self.running:
                return

            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=24000)

            pygame.mixer.music.load(temp_file)
            pygame.mixer.music.play()

            if blocking:
                while pygame.mixer.music.get_busy() and self.running and not self.interrupted:
                    time.sleep(0.03)

            if self.interrupted:
                try:
                    pygame.mixer.music.stop()
                except Exception:
                    pass

            # Release file lock before removal
            try:
                pygame.mixer.music.unload()
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception:
                pass

        except Exception as e:
            if not self.interrupted:
                # Fallback to SAPI voice if Edge TTS encounters network glitch
                try:
                    self.tts._speak_sapi(text, emotion="neutral", async_mode=not blocking)
                except Exception:
                    pass
        finally:
            if self.current_playing_file == temp_file:
                self.current_playing_file = None
            if not self.interrupted and blocking:
                # Brief natural breathing room before listening
                time.sleep(0.12)
            self.is_speaking = False

    async def start_conversation(self, text: str):
        """Dispatches user prompt, cancelling any previous active generation if interrupted."""
        if self._current_conv_task and not self._current_conv_task.done():
            self.stop_speaking()
            self._current_conv_task.cancel()
            try:
                await self._current_conv_task
            except (asyncio.CancelledError, Exception):
                pass

        self._current_conv_task = asyncio.create_task(self.converse(text))
        try:
            await self._current_conv_task
        except asyncio.CancelledError:
            pass

    async def converse(self, user_text: str):
        """Processes user input through reasoning loop and streams spoken response with live interruption."""
        self.interrupted = False
        self.is_processing = True

        full_reply = []
        sentence_buffer = ""
        spoken_sentences = set()

        print(f"\n{MAGENTA}{BOLD}Zohra:{RESET} ", end="", flush=True)

        try:
            async for event in assistant_brain.run_reasoning_loop(self.session_id, user_text):
                if self.interrupted:
                    print(f"\n{YELLOW}⚡ [Speech interrupted by user]{RESET}")
                    break

                if event["type"] == "token":
                    token = event["content"]
                    full_reply.append(token)
                    sentence_buffer += token
                    print(f"{CYAN}{token}{RESET}", end="", flush=True)

                    # Progressive natural sentence speech chunking
                    if any(punct in sentence_buffer for punct in [".", "!", "?", "।", "\n"]):
                        parts = sentence_buffer.replace("।", ".").replace("!", ".").replace("?", ".").replace("\n", ".").split(".")
                        if len(parts) > 1:
                            complete_sentence = parts[0].strip()
                            if len(complete_sentence) >= 10 or len(complete_sentence.split()) >= 3:
                                sentence_buffer = ".".join(parts[1:]).strip()
                                if complete_sentence and complete_sentence not in spoken_sentences:
                                    spoken_sentences.add(complete_sentence)
                                    if self.voice_enabled and not self.interrupted:
                                        await asyncio.to_thread(self.speak, complete_sentence, True)
                                        if self.interrupted:
                                            break

                elif event["type"] == "tool":
                    print(f"\n{YELLOW}  [Analyzing {event.get('name')}...]{RESET}", flush=True)

            # Speak any remaining buffer if not interrupted
            remaining = sentence_buffer.strip()
            if remaining and remaining not in spoken_sentences and self.voice_enabled and not self.interrupted:
                await asyncio.to_thread(self.speak, remaining, True)

            print()  # newline
        except asyncio.CancelledError:
            pass
        except Exception as err:
            print(f"\n{RED}[Error in conversational brain: {err}]{RESET}")
        finally:
            self.is_processing = False
            self.is_speaking = False
            print(f"\n{GREEN}🎙️ [Listening for your voice... speak anytime, or type below]{RESET}")

    def _audio_stream_callback(self, indata, frames, time_info, status):
        """Real-time microphone callback with full-duplex barge-in & adaptive noise floor."""
        if not self.is_listening:
            return

        # Compute RMS energy of this audio chunk
        samples = np.frombuffer(indata, dtype=np.int16).astype(np.float32)
        rms = float(np.sqrt(np.mean(samples**2)))

        # ─── CASE A: Zohra is speaking or processing (Barge-in / Interruption) ───
        if self.is_speaking or self.is_processing:
            if self.barge_in_enabled:
                # Require strong speech above speaker bleed to trigger interruption
                barge_threshold = max(self.vad_threshold * 1.55, self.vad_threshold + 65.0, 210.0)
                if rms >= barge_threshold:
                    self._barge_in_chunks += 1
                    if self._barge_in_chunks >= 2:  # ~100ms continuous voice confirms real interruption
                        self._barge_in_chunks = 0
                        self.stop_speaking()
                        self.is_processing = False
                        self._is_recording_utterance = True
                        self._speech_buffer = list(self._pre_buffer) + [indata.copy()]
                        self._silent_chunks = 0
                        self._speech_start_time = time.time()
                        print(f"\r{YELLOW}⚡ [Interruption detected — Zohra paused, listening to you...]{RESET}       ", end="", flush=True)
                        return
                else:
                    self._barge_in_chunks = 0
            return

        # ─── CASE B: Normal Listening State ───
        self._barge_in_chunks = 0

        # 1. Voice Detected (Speech Active)
        if rms >= self.vad_threshold:
            if not self._is_recording_utterance:
                self._is_recording_utterance = True
                self._speech_buffer = list(self._pre_buffer) + [indata.copy()]
                self._speech_start_time = time.time()
                print(f"\r{YELLOW}🎙️ [Voice detected (RMS: {rms:.0f}) ... listening]{RESET}       ", end="", flush=True)
            else:
                self._speech_buffer.append(indata.copy())
            self._silent_chunks = 0

        # 2. Silence Detected during an ongoing utterance
        elif self._is_recording_utterance:
            self._speech_buffer.append(indata.copy())
            self._silent_chunks += 1

            silence_duration = (self._silent_chunks * self.block_size) / self.sample_rate
            utterance_len = time.time() - self._speech_start_time
            # Adaptive snappy end-of-speech: 0.50s if speech > 1.2s, else 0.65s
            effective_silence = 0.50 if utterance_len >= 1.2 else self.silence_limit_seconds

            if silence_duration >= effective_silence:
                self._is_recording_utterance = False
                chunks_to_process = self._speech_buffer[:]
                self._speech_buffer = []
                self._silent_chunks = 0

                # Process this utterance in a background thread
                threading.Thread(target=self._process_recorded_speech, args=(chunks_to_process,), daemon=True).start()

        # 3. Idle Room Silence
        else:
            self._pre_buffer.append(indata.copy())

            # Dynamic Ambient Noise Floor tracking (slow EMA)
            if self.ambient_tracking_enabled and rms < self.vad_threshold * 0.85:
                self.noise_floor = float(0.97 * self.noise_floor + 0.03 * rms)
                calculated = max(self.noise_floor * 1.8, self.noise_floor + 45.0)
                self.vad_threshold = float(max(90.0, min(350.0, calculated)))

    def _process_recorded_speech(self, chunks):
        """Transcribes recorded microphone audio via Whisper and triggers conversation."""
        if not chunks or len(chunks) < 3:  # Ignore ultra-short clicks (<150ms)
            return

        raw_pcm = np.concatenate(chunks, axis=0).tobytes()

        # Check total volume to avoid background hum
        arr = np.frombuffer(raw_pcm, dtype=np.int16)
        utterance_rms = float(np.sqrt(np.mean(arr.astype(np.float32)**2)))
        if utterance_rms < self.noise_floor * 0.95:
            return

        print(f"\r{YELLOW}⚡ [Transcribing speech...]{RESET}                     ", end="", flush=True)

        try:
            transcript = self.stt.transcribe(raw_pcm)
            transcript = transcript.strip()

            # Ignore empty or punctuation-only Whisper hallucinations
            hallucinations = [
                "", ".", ",", "!", "?", "Thank you.", "Thank you", "Bye.", "Bye",
                "MBC", "Subtitles by", "You", "Watching", "Amara.org", "Okay.",
                "Thank you for watching.", "Thanks for watching!"
            ]
            if transcript in hallucinations or len(transcript) < 2:
                print(f"\r{GREEN}🎙️ [Listening for your voice... speak anytime, or type below]{RESET}")
                return

            print(f"\r{GREEN}{BOLD}You (Voice):{RESET} {CYAN}{transcript}{RESET}")

            # Trigger conversation loop
            loop = getattr(self, "_main_loop", None)
            if loop and loop.is_running():
                asyncio.run_coroutine_threadsafe(self.start_conversation(transcript), loop)
        except Exception as e:
            print(f"\n{RED}STT error: {e}{RESET}")
            print(f"{GREEN}🎙️ [Listening for your voice... speak anytime, or type below]{RESET}")

    def start_mic_stream(self):
        """Starts background microphone stream."""
        try:
            self._mic_stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                callback=self._audio_stream_callback,
                blocksize=self.block_size,
                device=self.input_device,
            )
            self._mic_stream.start()
            return True
        except Exception as e:
            print(f"{RED}Could not open microphone: {e}{RESET}")
            return False

    def list_input_devices(self):
        """Lists all available audio input devices."""
        print(f"\n{CYAN}{BOLD}--- AVAILABLE MICROPHONE DEVICES ---{RESET}")
        devs = sd.query_devices()
        default_in = sd.default.device[0]
        for idx, d in enumerate(devs):
            if d.get("max_input_channels", 0) > 0:
                is_active = (idx == self.input_device) or (self.input_device is None and idx == default_in)
                marker = f"{GREEN}* [ACTIVE]{RESET}" if is_active else " "
                print(f"  {marker} [{idx}] {d['name']} (Channels: {d['max_input_channels']})")
        print(f"{CYAN}Use 'mic <id>' to switch devices (e.g. 'mic 1' or 'mic 14'){RESET}\n")

    def switch_input_device(self, device_id: int):
        """Switches active input microphone on the fly."""
        try:
            dev_info = sd.query_devices(device_id)
            if dev_info.get("max_input_channels", 0) <= 0:
                print(f"{RED}Device [{device_id}] is not an audio input device.{RESET}")
                return False

            if hasattr(self, "_mic_stream") and self._mic_stream:
                self._mic_stream.stop()
                self._mic_stream.close()

            self.input_device = device_id
            print(f"{GREEN}Switched to microphone [{device_id}]: {dev_info['name']}{RESET}")
            self.calibrate_mic(0.6)
            return self.start_mic_stream()
        except Exception as e:
            print(f"{RED}Failed to switch microphone device: {e}{RESET}")
            return False

    def print_status(self):
        """Prints live companion status and diagnostic telemetry."""
        barge_str = f"{GREEN}ENABLED (Speak anytime to interrupt){RESET}" if self.barge_in_enabled else f"{RED}DISABLED{RESET}"
        voice_desc = VOICE_CATALOG.get(
            next((k for k, v in VOICE_CATALOG.items() if v[0] == self.selected_voice), ""),
            (self.selected_voice, self.selected_voice)
        )[1]
        active_mic = sd.query_devices(self.input_device if self.input_device is not None else sd.default.device[0])['name']

        print(f"""
{CYAN}{BOLD}--- ZOHRA COMPANION LIVE STATUS ---{RESET}
  Ambient Noise Floor   : {self.noise_floor:.1f} RMS (Dynamic tracking: {'ON' if self.ambient_tracking_enabled else 'OFF'})
  VAD Trigger Threshold : {self.vad_threshold:.1f} RMS
  Silence Turnaround    : {self.silence_limit_seconds:.2f}s (Fast human response)
  Barge-In Interruption : {barge_str}
  Active Neural Voice   : {self.selected_voice}
                          ({voice_desc})
  Active Microphone     : {active_mic}
  Audio Output Speaker  : {'ENABLED' if self.voice_enabled else 'MUTED'}
""")


async def main():
    print(f"""
{CYAN}{BOLD}══════════════════════════════════════════════════════════════════════════════
  ✦ ZOHRA AI — REAL-TIME TWO-WAY VOICE COMPANION (JARVIS) ✦
  Model      : OpenRouter openai/gpt-4o-mini
  Voice TTS  : Microsoft Ava Multilingual Neural (World-class multilingual studio voice)
  Voice STT  : Cloud Whisper Turbo (Groq ~150ms transcription)
  Full-Duplex: Active Barge-In Interruption Enabled (Interrupt Zohra anytime!)
══════════════════════════════════════════════════════════════════════════════{RESET}
  Voice Commands:
    Simply speak aloud naturally, or type your message and press Enter!
    'status'          : Display system telemetry & sensitivity metrics
    'barge on/off'    : Toggle barge-in voice interruption
    'voice ava'       : Set Ava Multilingual (Default - Premier Natural Multilingual)
    'voice emma'      : Set Emma Multilingual (Expressive Natural Multilingual)
    'voice swara'     : Set Swara (Pure Indian Hindi)
    'voice uzma'      : Set Uzma (Pure Pakistani Urdu)
    'voice neerja'    : Set Neerja (Indian English)
    'voice list'      : View all available voice models
    'mic'             : List input microphone devices
    'mic <id>'        : Switch microphone device (e.g., 'mic 1' or 'mic 14')
    'calibrate'       : Re-calibrate microphone sensitivity
    'threshold <num>' : Set sensitivity threshold manually (e.g. 'threshold 130')
    'silence <sec>'   : Set silence turnaround limit (e.g. 'silence 0.6')
    'voice mute/on'   : Toggle audio speaker output
    'exit' or 'quit'  : Exit conversation
""")

    companion = ZohraLiveVoiceCompanion()
    companion._main_loop = asyncio.get_running_loop()

    # Step 1: Calibrate microphone noise floor
    companion.calibrate_mic(0.7)

    # Step 2: Start live mic listener
    mic_ok = companion.start_mic_stream()
    if mic_ok:
        active_name = sd.query_devices(sd.default.device[0])['name']
        print(f"{GREEN}✓ Microphone is ACTIVE [{active_name}]. Speak aloud naturally (Barge-in active)!{RESET}")
    else:
        print(f"{YELLOW}⚠ Microphone could not start automatically. You can type below.{RESET}")

    # Initial human greeting from Zohra
    greeting = "Hello Sir! Zohra is online. Main aapki baat sun sakti hoon aur har zabaan mein bol sakti hoon. How can I assist you today?"
    print(f"\n{MAGENTA}{BOLD}Zohra:{RESET} {CYAN}{greeting}{RESET}")
    await asyncio.to_thread(companion.speak, greeting, True)

    print(f"\n{GREEN}🎙️ [Listening for your voice... speak anytime, or type below]{RESET}")

    # Keyboard input handler runs concurrently with mic listener
    while companion.running:
        try:
            line = await asyncio.to_thread(sys.stdin.readline)
            if not line:
                break
            user_input = line.strip()

            if not user_input:
                continue

            lowered = user_input.lower()

            if lowered in ["exit", "quit", "q"]:
                companion.running = False
                companion.stop_speaking()
                farewell = "Goodbye Sir! Have a profitable trading session."
                print(f"\n{MAGENTA}{BOLD}Zohra:{RESET} {CYAN}{farewell}{RESET}")
                await asyncio.to_thread(companion.speak, farewell, True)
                break

            if lowered == "status":
                companion.print_status()
                continue

            if lowered == "barge on":
                companion.barge_in_enabled = True
                print(f"{GREEN}Barge-in enabled: You can interrupt Zohra while she speaks.{RESET}")
                continue

            if lowered == "barge off":
                companion.barge_in_enabled = False
                print(f"{YELLOW}Barge-in disabled: Zohra will speak without listening for interruptions.{RESET}")
                continue

            if lowered.startswith("silence "):
                try:
                    s_val = float(lowered.split()[1])
                    companion.silence_limit_seconds = max(0.3, min(2.0, s_val))
                    print(f"{GREEN}Silence turnaround limit set to {companion.silence_limit_seconds:.2f}s{RESET}")
                except Exception:
                    print(f"{RED}Usage: silence 0.6{RESET}")
                continue

            if lowered == "voice mute":
                companion.voice_enabled = False
                companion.stop_speaking()
                print(f"{YELLOW}Speaker output muted.{RESET}")
                continue

            if lowered == "voice on":
                companion.voice_enabled = True
                print(f"{YELLOW}Speaker output enabled.{RESET}")
                continue

            if lowered == "voice list":
                print(f"\n{CYAN}{BOLD}--- AVAILABLE STUDIO NEURAL VOICES ---{RESET}")
                for alias, (vname, desc) in VOICE_CATALOG.items():
                    active_marker = f"{GREEN}* [ACTIVE]{RESET}" if companion.selected_voice == vname else " "
                    print(f"  {active_marker} 'voice {alias}' -> {desc}")
                print()
                continue

            if lowered.startswith("voice "):
                alias = lowered.split()[1]
                if alias in VOICE_CATALOG:
                    vname, desc = VOICE_CATALOG[alias]
                    companion.selected_voice = vname
                    print(f"{GREEN}Voice updated to: {desc}{RESET}")
                    sample_text = f"Voice changed to {alias}. Main is aawaz mein baat kar sakti hoon."
                    await asyncio.to_thread(companion.speak, sample_text, True)
                else:
                    print(f"{YELLOW}Unknown voice alias '{alias}'. Type 'voice list' to see all voices.{RESET}")
                continue

            if lowered in ["mic", "mic list"]:
                companion.list_input_devices()
                continue

            if lowered.startswith("mic "):
                try:
                    dev_id = int(lowered.split()[1])
                    companion.switch_input_device(dev_id)
                except Exception:
                    print(f"{RED}Usage: mic <device_id> (e.g., mic 1){RESET}")
                continue

            if lowered == "calibrate":
                companion.calibrate_mic(0.8)
                continue

            if lowered.startswith("threshold "):
                try:
                    val = float(lowered.split()[1])
                    companion.vad_threshold = val
                    print(f"{YELLOW}Microphone sensitivity threshold set to: {val:.1f} RMS{RESET}")
                except Exception:
                    print(f"{RED}Usage: threshold 130{RESET}")
                continue

            # Process typed input with instant cancellation of previous speech
            print(f"{GREEN}{BOLD}You (Text):{RESET} {user_input}")
            await companion.start_conversation(user_input)

        except (KeyboardInterrupt, EOFError):
            break
        except Exception as e:
            print(f"{RED}Error: {e}{RESET}")

    # Cleanup
    try:
        companion.stop_speaking()
        if hasattr(companion, "_mic_stream") and companion._mic_stream:
            companion._mic_stream.stop()
            companion._mic_stream.close()
    except Exception:
        pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
