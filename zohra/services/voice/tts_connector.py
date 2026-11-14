# ZOHRA OS — Text-To-Speech Connector (TTS Router)
import logging
import os
import subprocess
import tempfile
import threading

logger = logging.getLogger("zohra.voice.tts")

# Emotional profiles mapping (kept for backward compatibility with voice framework)
EMOTION_MAP = {
    "neutral": {"stability": 0.65, "similarity_boost": 0.75, "style": 0.0},
    "professional": {"stability": 0.80, "similarity_boost": 0.75, "style": 0.0},
    "analytical": {"stability": 0.80, "similarity_boost": 0.75, "style": 0.0},
    "friendly": {"stability": 0.55, "similarity_boost": 0.80, "style": 0.10},
    "calm": {"stability": 0.85, "similarity_boost": 0.75, "style": 0.0},
    "concerned": {"stability": 0.75, "similarity_boost": 0.70, "style": 0.0},
    "serious": {"stability": 0.75, "similarity_boost": 0.70, "style": 0.0},
    "excited": {"stability": 0.45, "similarity_boost": 0.85, "style": 0.20},
    "celebratory": {"stability": 0.45, "similarity_boost": 0.85, "style": 0.20}
}

# Speaking rate adjustments per emotion
EMOTION_RATES = {
    "neutral": 180,
    "professional": 180,
    "analytical": 180,
    "friendly": 180,
    "calm": 150,
    "concerned": 150,
    "serious": 150,
    "excited": 210,
    "celebratory": 210
}

def ends_sentence(text: str) -> bool:
    trimmed = text.strip()
    return len(trimmed) > 0 and trimmed[-1] in (".", "!", "?", "\n")

MAX_BUFFER_CHARS = 100

class TTSConnector:
    """
    Text-To-Speech Connector supporting:
    - Local: Windows speech or pyttsx3 with an installed female voice
    - Raises an availability error when no real local speech engine exists
    """
    async def stream_tts(self, text_stream, emotion: str = "neutral"):
        """Assembles streaming tokens into sentences and synthesizes them in real-time."""
        buffer = ""
        async for token in text_stream:
            buffer += token
            if ends_sentence(buffer) or len(buffer) > MAX_BUFFER_CHARS:
                # Synthesize the buffer
                audio_chunk = self.synthesize(buffer, emotion)
                yield audio_chunk
                buffer = ""
        if buffer.strip():
            audio_chunk = self.synthesize(buffer, emotion)
            yield audio_chunk

    def __init__(self, provider: str = "local"):
        self.provider = "local"
        self.local_engine = None
        self.selected_voice = None
        self.backend = None
        self._engine_lock = threading.Lock()
        self._init_local_tts()
        if self.available:
            logger.info("Local TTS ready: %s (%s)", self.selected_voice, self.backend)

    @property
    def available(self) -> bool:
        return bool(self.selected_voice and self.backend)

    @staticmethod
    def _windows_female_voice() -> str | None:
        if os.name != "nt":
            return None
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$voices = @($s.GetInstalledVoices() | Where-Object "
            "{ $_.VoiceInfo.Gender -eq [System.Speech.Synthesis.VoiceGender]::Female } "
            "| ForEach-Object { $_.VoiceInfo.Name }); "
            "$preferred = $env:ZOHRA_TTS_VOICE; "
            "$choice = $voices | Where-Object { $_ -eq $preferred } | Select-Object -First 1; "
            "if (-not $choice) { $choice = $voices | Where-Object { $_ -match 'Zira' } "
            "| Select-Object -First 1 }; "
            "if (-not $choice) { $choice = $voices | Select-Object -First 1 }; "
            "if ($choice) { [Console]::WriteLine($choice) }; $s.Dispose()"
        )
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Sta", "-Command", script],
                capture_output=True, text=True, timeout=10, check=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode:
                logger.warning("Windows female voice lookup returned %s: %s",
                               result.returncode, result.stderr.strip()[:300])
            elif not result.stdout.strip():
                logger.warning("Windows female voice lookup returned no voice: %s",
                               result.stderr.strip()[:300])
            return result.stdout.strip().splitlines()[0] if result.returncode == 0 and result.stdout.strip() else None
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("Windows female voice lookup failed: %s", exc)
            return None

    def _init_local_tts(self):
        # 1. Try Microsoft Edge Neural Voice (Ultra-realistic, multilingual human voice)
        try:
            import edge_tts
            import pygame
            pygame.mixer.init()
            preferred = os.getenv("ZOHRA_TTS_VOICE", "en-US-AvaMultilingualNeural")
            self.selected_voice = preferred
            self.backend = "edge-tts"
            logger.info("Edge Neural Voice initialized: %s", self.selected_voice)
            return
        except Exception as exc:
            logger.warning("Edge Neural Voice init failed: %s, checking Windows SAPI", exc)

        # 2. Try direct Windows SAPI via COM (fastest offline fallback)
        if os.name == "nt":
            try:
                import win32com.client
                voice = win32com.client.Dispatch("SAPI.SpVoice")
                voices = voice.GetVoices()
                preferred = os.getenv("ZOHRA_TTS_VOICE", "").lower()
                selected = None
                for v in voices:
                    desc = v.GetDescription()
                    if preferred and preferred in desc.lower():
                        selected = v
                        break
                    if "zira" in desc.lower():
                        selected = v
                if not selected and len(voices) > 0:
                    selected = voices[0]
                if selected:
                    voice.Voice = selected
                    self.selected_voice = selected.GetDescription()
                    self.backend = "direct-sapi"
                    logger.info("Direct SAPI voice initialized: %s", self.selected_voice)
                    return
            except Exception as exc:
                logger.warning("Direct SAPI COM init failed: %s, checking alternatives", exc)

        # 3. Try PowerShell System.Speech
        self.selected_voice = self._windows_female_voice()
        if self.selected_voice:
            self.backend = "windows-sapi"
            return

        # 4. Fallback to pyttsx3
        try:
            import pyttsx3
            engine = pyttsx3.init()
            voices = engine.getProperty("voices") or []
            female_names = ("zira", "hazel", "heera", "samantha", "aria", "jenny", "ava")
            female = [voice for voice in voices if
                      str(getattr(voice, "gender", "")).lower().strip("b'\"") == "female" or
                      any(name in str(getattr(voice, "name", "")).lower() for name in female_names)]
            preferred = os.getenv("ZOHRA_TTS_VOICE", "").lower()
            female.sort(key=lambda voice: (
                0 if preferred and preferred in voice.name.lower() else 1,
                0 if "zira" in voice.name.lower() else 1,
            ))
            if female:
                engine.setProperty("voice", female[0].id)
                engine.setProperty("volume", 0.9)
                self.local_engine = engine
                self.selected_voice = female[0].name
                self.backend = "pyttsx3"
            elif voices:
                engine.setProperty("voice", voices[0].id)
                self.local_engine = engine
                self.selected_voice = voices[0].name
                self.backend = "pyttsx3"
            else:
                logger.warning("No local speech voice is installed")
        except Exception as exc:
            logger.warning("Local text-to-speech unavailable: %s", exc)

    def synthesize(self, text: str, emotion: str = "neutral") -> bytes:
        """Synthesizes text into audio binary buffer using the configured provider."""
        return self._synthesize_local(text, emotion)

    def speak(self, text: str, emotion: str = "neutral", async_mode: bool = False):
        """Directly speaks the text out loud over local speakers."""
        if not self.available:
            return

        # 1. Edge Neural Voice Playback
        if self.backend == "edge-tts":
            def _play_edge():
                try:
                    import asyncio, edge_tts, pygame
                    if not pygame.mixer.get_init():
                        pygame.mixer.init()
                    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                        temp_file = f.name
                    async def _gen():
                        comm = edge_tts.Communicate(text, self.selected_voice)
                        await comm.save(temp_file)
                    asyncio.run(_gen())
                    pygame.mixer.music.load(temp_file)
                    pygame.mixer.music.play()
                    if not async_mode:
                        while pygame.mixer.music.get_busy():
                            time.sleep(0.05)
                except Exception as e:
                    logger.warning("Edge TTS playback error: %s, falling back to SAPI", e)
                    self._speak_sapi(text, emotion, async_mode)

            if async_mode:
                threading.Thread(target=_play_edge, daemon=True).start()
            else:
                _play_edge()
            return

        # 2. SAPI Playback
        self._speak_sapi(text, emotion, async_mode)

    def _speak_sapi(self, text: str, emotion: str = "neutral", async_mode: bool = False):
        rate = EMOTION_RATES.get(emotion.lower(), 180)
        sapi_rate = max(-10, min(10, round((rate - 180) / 15)))
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass
        try:
            import win32com.client
            v = win32com.client.Dispatch("SAPI.SpVoice")
            for item in v.GetVoices():
                if "zira" in item.GetDescription().lower():
                    v.Voice = item
                    break
            v.Rate = sapi_rate
            flags = 1 if async_mode else 0
            v.Speak(text, flags)
            v = None
            return
        except Exception as e:
            logger.warning("Direct SAPI speak failed: %s", e)
        finally:
            v = None
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass

    def _synthesize_local(self, text: str, emotion: str) -> bytes:
        """Local/Neural TTS synthesis with native OS engine, adapting speaking rate to emotion."""
        if not self.available:
            raise RuntimeError("A female text-to-speech voice is unavailable")

        if self.backend == "edge-tts":
            try:
                import asyncio, edge_tts
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                    temp_mp3 = f.name
                async def _gen():
                    comm = edge_tts.Communicate(text, self.selected_voice)
                    await comm.save(temp_mp3)
                asyncio.run(_gen())
                with open(temp_mp3, "rb") as af:
                    data = af.read()
                try:
                    os.remove(temp_mp3)
                except Exception:
                    pass
                if len(data) > 100:
                    return data
            except Exception as e:
                logger.warning("Edge TTS synthesis failed: %s, falling back to SAPI", e)

        rate = EMOTION_RATES.get(emotion.lower(), 180)
        sapi_rate = max(-10, min(10, round((rate - 180) / 15)))
        with tempfile.TemporaryDirectory(prefix="zohra-tts-") as temp_dir:
            output = os.path.join(temp_dir, "speech.wav")
            if self.backend in ("direct-sapi", "edge-tts"):
                voice = None
                stream = None
                try:
                    import pythoncom
                    pythoncom.CoInitialize()
                except Exception:
                    pass
                try:
                    import win32com.client
                    voice = win32com.client.Dispatch("SAPI.SpVoice")
                    for v in voice.GetVoices():
                        if v.GetDescription() == self.selected_voice:
                            voice.Voice = v
                            break
                    voice.Rate = sapi_rate
                    stream = win32com.client.Dispatch("SAPI.SpFileStream")
                    stream.Open(output, 3, False)  # 3 = SSFMCreateForWrite
                    voice.AudioOutputStream = stream
                    voice.Speak(text)
                    stream.Close()
                finally:
                    voice = None
                    stream = None
                    try:
                        import pythoncom
                        pythoncom.CoUninitialize()
                    except Exception:
                        pass
            elif self.backend == "windows-sapi":
                script = (
                    "Add-Type -AssemblyName System.Speech; "
                    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                    "try { "
                    "$s.SelectVoice($env:ZOHRA_TTS_SELECTED); "
                    "$s.Rate = [int]$env:ZOHRA_TTS_RATE; "
                    "$s.SetOutputToWaveFile($env:ZOHRA_TTS_OUTPUT); "
                    "[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false); "
                    "$s.Speak([Console]::In.ReadToEnd()); "
                    "} finally { $s.Dispose() }"
                )
                env = os.environ.copy()
                env.update(ZOHRA_TTS_SELECTED=self.selected_voice,
                           ZOHRA_TTS_OUTPUT=output,
                           ZOHRA_TTS_RATE=str(sapi_rate))
                result = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-NonInteractive", "-Sta", "-Command", script],
                    input=text.encode("utf-8"), capture_output=True, env=env, timeout=30,
                    check=False, creationflags=subprocess.CREATE_NO_WINDOW,
                )
                if result.returncode:
                    raise RuntimeError("Windows speech synthesis failed")
            else:
                with self._engine_lock:
                    self.local_engine.setProperty("rate", rate)
                    self.local_engine.save_to_file(text, output)
                    self.local_engine.runAndWait()
            if not os.path.exists(output):
                raise RuntimeError("Local text-to-speech produced no audio")
            with open(output, "rb") as wav_file:
                data = wav_file.read()
            if not data.startswith(b"RIFF") or len(data) < 100:
                raise RuntimeError("Local text-to-speech produced invalid audio")
            return data
