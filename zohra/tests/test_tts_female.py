from types import SimpleNamespace
from unittest.mock import patch

from zohra.services.voice.tts_connector import TTSConnector


def test_male_default_is_not_used_without_female_voice():
    male = SimpleNamespace(name="David", id="male", gender="Male")
    engine = SimpleNamespace(
        getProperty=lambda name: [male],
        setProperty=lambda *args: None,
    )
    fake_pyttsx3 = SimpleNamespace(init=lambda: engine)
    with patch.object(TTSConnector, "_windows_female_voice", return_value=None), patch.dict(
        "sys.modules", {"pyttsx3": fake_pyttsx3}
    ):
        connector = TTSConnector()
    assert not connector.available
    try:
        connector.synthesize("hello")
    except RuntimeError as exc:
        assert "female" in str(exc).lower()
    else:
        raise AssertionError("male default voice was silently accepted")


def test_windows_female_voice_returns_real_wav_bytes():
    wav = b"RIFF" + bytes(128)
    with patch.object(TTSConnector, "_windows_female_voice", return_value="Microsoft Zira Desktop"):
        connector = TTSConnector()

    def synthesize(command, **kwargs):
        assert kwargs["env"]["ZOHRA_TTS_SELECTED"] == "Microsoft Zira Desktop"
        assert kwargs["input"] == "Hello Zohra".encode("utf-8")
        with open(kwargs["env"]["ZOHRA_TTS_OUTPUT"], "wb") as output:
            output.write(wav)
        return SimpleNamespace(returncode=0)

    with patch("subprocess.run", side_effect=synthesize):
        assert connector.synthesize("Hello Zohra") == wav
