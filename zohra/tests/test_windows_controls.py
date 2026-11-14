"""Isolated adapter/approval tests. Fakes never change the host audio/display settings."""
import asyncio
import json
import time

import pytest
from pydantic import ValidationError

from zohra.services.automation.windows_controls import (
    AudioChange, BrightnessChange, NativeControlError, audio_status, display_status,
    prepare_control, execute_control,
)
from zohra.services.tool_execution.state import CapabilityStore


@pytest.fixture(autouse=True)
def isolated_native_health(tmp_path, monkeypatch):
    monkeypatch.setenv("ZOHRA_ASSISTANT_WORKSPACE", str(tmp_path / "native-health"))


class Audio:
    def __init__(self):
        self.data = {"device_id":"speaker-1", "device_name":"Test speakers", "volume":50.0, "muted":False}
        self.applied = []

    def snapshot(self):
        return dict(self.data)

    def apply(self, args):
        if args.device_id != self.data["device_id"]:
            raise NativeControlError("STALE_DEVICE", "Device changed")
        if abs(args.previous_volume - self.data["volume"]) > .6 or args.previous_muted != self.data["muted"]:
            raise NativeControlError("STALE_STATE", "Setting changed")
        self.applied.append(args.model_dump())
        if args.volume is not None:
            self.data["volume"] = float(args.volume)
        else:
            self.data["muted"] = args.muted


class Display:
    def __init__(self):
        self.data = [{"monitor_id":"monitor-1", "brightness":40, "levels":list(range(101))}]
        self.applied = []

    def snapshot(self):
        return [dict(row) for row in self.data]

    def apply(self, args):
        self.applied.append(args.model_dump())
        self.data[0]["brightness"] = args.brightness


def approval(tmp_path, action, args, status="executing", session="test", expires=None):
    store = CapabilityStore(tmp_path)
    with store.session() as db:
        db.execute("CREATE TABLE confirmations(id TEXT PRIMARY KEY, session TEXT, action TEXT, args TEXT, status TEXT, expires INTEGER)")
        db.execute("INSERT INTO confirmations VALUES(?,?,?,?,?,?)", ("approved-id",session,action,json.dumps(args),status,expires or time.time()*1000+300000))
    return store, {"id":"approved-id","session":"test"}


@pytest.mark.parametrize("raw", [{}, {"volume":True}, {"volume":"40"}, {"volume":101}, {"volume":-1},
    {"muted":"true"}, {"volume":40,"muted":False}, {"volume":40,"simulated_elevation_approved":True}])
def test_audio_parameters_are_strict_and_cannot_carry_authority(raw):
    with pytest.raises(ValidationError):
        AudioChange.model_validate(raw)


@pytest.mark.parametrize("raw", [{"brightness":True}, {"brightness":"10"}, {"brightness":101}, {"brightness":-1}, {"brightness":10,"monitor_id":""}])
def test_display_parameters_are_strict(raw):
    with pytest.raises(ValidationError):
        BrightnessChange.model_validate(raw)


def test_previews_are_real_reads_and_do_not_mutate():
    audio, display = Audio(), Display()
    result = prepare_control("configure_audio", {"volume":25}, audio=audio)
    assert result["args"]["device_id"] == "speaker-1" and result["args"]["previous_volume"] == 50
    assert "25%" in result["description"] and "50.0%" in result["consequence"]
    brightness = prepare_control("configure_brightness", {"brightness":10}, display=display)
    assert brightness["args"]["monitor_id"] == "monitor-1" and brightness["args"]["previous_brightness"] == 40
    assert audio.applied == display.applied == []
    assert audio_status(audio)["observed_at"] and display_status(display)["observed_at"]


@pytest.mark.parametrize("requested", [{"volume":25}, {"muted":True}, {"muted":False}])
def test_confirmed_audio_changes_are_verified_and_single_use(tmp_path, requested):
    audio = Audio()
    args = prepare_control("configure_audio",requested,audio=audio)["args"]
    store, token = approval(tmp_path,"configure_audio",args)
    result = execute_control("configure_audio",args,token,store,audio=audio)
    assert result["verified"] and len(audio.applied) == 1
    with pytest.raises(NativeControlError,match="already consumed"):
        execute_control("configure_audio",args,token,store,audio=audio)
    assert len(audio.applied) == 1


def test_brightness_readback_confirms_exact_monitor(tmp_path):
    display = Display()
    args = prepare_control("configure_brightness",{"brightness":10},display=display)["args"]
    store, token = approval(tmp_path,"configure_brightness",args)
    result = execute_control("configure_brightness",args,token,store,display=display)
    assert result["verified"] and result["after"]["brightness"] == 10


@pytest.mark.parametrize("response", [(0, '{"ok":true}'), (1, '{"ok":false,"error":"WMI access denied"}'), (0, 'invalid'), (0, '{}')])
def test_native_brightness_uses_fixed_typed_cim_and_rejects_failed_outputs(tmp_path, monkeypatch, response):
    from types import SimpleNamespace
    from zohra.services.automation import windows_controls as controls
    from zohra.services.automation.windows_controls import WmiBrightness
    monkeypatch.setattr(controls, "require_windows", lambda: None)
    monkeypatch.setattr(controls.subprocess, "CREATE_NO_WINDOW", 0, raising=False)
    calls = []
    current = {"monitor_id":"monitor-1", "brightness":40, "levels":[]}
    def run(command, **options):
        assert command[-1] == controls.BRIGHTNESS_COMMAND
        assert "$parameters['Brightness'] = [byte]$request.brightness" in command[-1]
        assert json.loads(options["input"]) == args
        assert "monitor-1" not in command[-1] and not options.get("shell")
        calls.append(command)
        current["brightness"] = 10
        return SimpleNamespace(returncode=response[0], stdout=response[1], stderr="")
    monkeypatch.setattr(controls.subprocess, "run", run)
    backend = WmiBrightness()
    backend.snapshot = lambda: [dict(current)]
    args = prepare_control("configure_brightness", {"brightness":10}, display=backend)["args"]
    store, token = approval(tmp_path, "configure_brightness", args)
    if response == (0, '{"ok":true}'):
        result = execute_control("configure_brightness", args, token, store, display=backend)
        assert result["verified"] and result["after"]["brightness"] == 10
    else:
        with pytest.raises(NativeControlError):
            execute_control("configure_brightness", args, token, store, display=backend)
    assert len(calls) == 1


@pytest.mark.parametrize("failure", ["pending", "expired", "wrong_session", "modified_args", "revoked", "no_token"])
def test_unapproved_native_requests_cannot_touch_hardware(tmp_path, failure):
    audio = Audio()
    args = prepare_control("configure_audio",{"volume":25},audio=audio)["args"]
    store, token = approval(tmp_path,"configure_audio",args,status="pending" if failure == "pending" else "executing",
        session="other" if failure == "wrong_session" else "test", expires=1 if failure == "expired" else None)
    if failure == "modified_args":
        args["volume"] = 80
    if failure == "revoked":
        with store.session() as db:
            db.execute("INSERT INTO tool_controls VALUES('windows.audio',0,'now')")
    with pytest.raises(NativeControlError):
        execute_control("configure_audio",args,None if failure == "no_token" else token,store,audio=audio)
    assert audio.applied == []


@pytest.mark.parametrize("changed", ["device", "volume", "mute"])
def test_device_or_setting_changes_invalidate_approved_audio(tmp_path, changed):
    audio = Audio()
    args = prepare_control("configure_audio",{"volume":25},audio=audio)["args"]
    store, token = approval(tmp_path,"configure_audio",args)
    audio.data[{"device":"device_id","volume":"volume","mute":"muted"}[changed]] = {"device":"other","volume":70.0,"mute":True}[changed]
    with pytest.raises(NativeControlError):
        execute_control("configure_audio",args,token,store,audio=audio)
    assert audio.applied == []


def test_failed_hardware_readback_never_reports_completion(tmp_path):
    audio = Audio()
    args = prepare_control("configure_audio",{"volume":25},audio=audio)["args"]
    store, token = approval(tmp_path,"configure_audio",args)
    audio.apply = lambda args: None
    with pytest.raises(NativeControlError,match="did not match"):
        execute_control("configure_audio",args,token,store,audio=audio)
    from zohra.services.automation.windows_controls import native_fault
    assert native_fault("audio", store)
    with pytest.raises(NativeControlError,match="writes blocked"):
        execute_control("configure_audio",args,token,store,audio=audio)


def test_failed_native_control_stays_blocked_but_read_only_status_remains(monkeypatch):
    from zohra.services.automation import windows_controls as controls
    from zohra.services.tool_execution.registry import CapabilityState
    controls.record_native_fault("display", "Driver returned an incorrect brightness; operator diagnosis required")
    monkeypatch.setattr(controls, "native_dependencies", lambda kind: (CapabilityState.AVAILABLE, "Installed"))
    assert controls.native_control_availability("display")[0] == CapabilityState.EXECUTION_FAILED
    assert controls.display_status(Display())["monitors"]
    with pytest.raises(NativeControlError, match="incorrect brightness"):
        prepare_control("configure_brightness", {"brightness":10}, display=Display())
    assert controls.native_control_availability("audio")[0] == CapabilityState.AVAILABLE


def test_display_transition_polls_reads_without_repeating_the_write(tmp_path, monkeypatch):
    from zohra.services.automation import windows_controls as controls
    display = Display()
    args = prepare_control("configure_brightness", {"brightness":10}, display=display)["args"]
    store, token = approval(tmp_path, "configure_brightness", args)
    values = iter([40, 10])
    display.snapshot = lambda: [{"monitor_id":"monitor-1", "brightness":next(values)}]
    monkeypatch.setattr(controls.time, "sleep", lambda duration: None)
    result = execute_control("configure_brightness", args, token, store, display=display)
    assert result["verified"] and len(display.applied) == 1


def test_multiple_monitors_require_an_exact_choice():
    display = Display()
    display.data.append({"monitor_id":"monitor-2","brightness":70,"levels":[]})
    with pytest.raises(NativeControlError,match="exact active monitor"):
        prepare_control("configure_brightness",{"brightness":10},display=display)
    assert prepare_control("configure_brightness",{"brightness":10,"monitor_id":"monitor-2"},display=display)["args"]["previous_brightness"] == 70


def test_voice_uses_the_same_confirmation_gate_and_never_self_confirms(tmp_path, monkeypatch):
    from zohra.services.chat import assistant_orchestrator as orchestrator
    from zohra.services.chat.assistant_store import AssistantStore
    monkeypatch.setenv("ZOHRA_ASSISTANT_WORKSPACE",str(tmp_path / "runtime"))
    monkeypatch.setattr(orchestrator,"assistant_store",AssistantStore(tmp_path / "history.db"))

    async def turn(text):
        return [event async for event in orchestrator.voice_events("voice-test",text)]

    events = asyncio.run(turn('write file "voice.txt" with approved voice test'))
    result = next(event["result"] for event in events if event["type"] == "assistant_result")
    assert result["status"] == "pending_confirmation"
    target = tmp_path / "runtime" / "files" / "voice.txt"
    assert not target.exists()
    confirmation = asyncio.run(turn("confirm"))
    assert next(event["result"] for event in confirmation if event["type"] == "assistant_result")["execution"]["verified"]
    assert target.read_text() == "approved voice test"
    assert asyncio.run(turn("close all trades"))[1]["result"]["status"] == "blocked"


@pytest.mark.parametrize("peer,hostname,origin", [("192.0.2.10","127.0.0.1",None),("127.0.0.1","evil.example",None),("127.0.0.1","127.0.0.1","https://evil.example")])
def test_voice_write_surface_rejects_unpaired_peers_and_wrong_origins(peer, hostname, origin):
    from types import SimpleNamespace
    from zohra.api.voice_router import voice_stream_endpoint
    closed = []
    class Socket:
        headers = {"host":"127.0.0.1:8011", **({"origin":origin} if origin else {})}
        url = SimpleNamespace(hostname=hostname,scheme="ws")
        client = SimpleNamespace(host=peer)
        async def close(self,code):
            closed.append(code)
        async def accept(self):
            pytest.fail("Unpaired voice client must not be accepted")
    asyncio.run(voice_stream_endpoint(Socket(),"voice-test"))
    assert closed == [1008]


def test_transcribed_voice_write_requires_a_second_utterance(tmp_path, monkeypatch):
    from unittest.mock import MagicMock
    from zohra.services.voice.voice_gateway import VoiceGatewayService
    from zohra.services.chat import assistant_orchestrator as orchestrator
    from zohra.services.chat.assistant_store import AssistantStore
    monkeypatch.setenv("ZOHRA_ASSISTANT_WORKSPACE",str(tmp_path / "runtime"))
    monkeypatch.setattr(orchestrator,"assistant_store",AssistantStore(tmp_path / "history.db"))
    gateway = VoiceGatewayService.__new__(VoiceGatewayService)
    gateway.stt = MagicMock()
    gateway.stt.transcribe.side_effect = ['write file "speech.txt" with separate voice approval','confirm']
    gateway.speaker_id = MagicMock()
    gateway.speaker_id.identify_speaker.return_value = ("Guest",0,"guest")
    gateway.voice_memory = MagicMock()
    gateway.voice_memory.apply_pronunciation.side_effect = lambda value:value
    gateway.tts = MagicMock()
    gateway.tts.synthesize.return_value = b"RIFF-test-audio"
    events = []
    class Socket:
        async def send_text(self,value):
            events.append(json.loads(value))
        async def send_bytes(self,value):
            pass
    target = tmp_path / "runtime" / "files" / "speech.txt"
    asyncio.run(gateway._generate_and_stream_response(Socket(),"speech-test",b"simulated-pcm"))
    assert not target.exists()
    assert next(event["result"] for event in events if event["type"] == "assistant_result")["status"] == "pending_confirmation"
    asyncio.run(gateway._generate_and_stream_response(Socket(),"speech-test",b"simulated-confirm-pcm"))
    assert target.read_text() == "separate voice approval"
    gateway.speaker_id.voice_authenticate.assert_not_called()
    assert [event["result"]["status"] for event in events if event["type"] == "assistant_result"] == ["pending_confirmation","success"]
