"""Native user-session controls; mutation requires an exact, single-use bridge approval."""
import importlib.util
import json
import os
import platform
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from zohra.services.tool_execution.state import CapabilityStore


BRIGHTNESS_COMMAND = r"""
$ErrorActionPreference = 'Stop'
try {
    $request = [Console]::In.ReadToEnd() | ConvertFrom-Json
    $active = @(Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightness | Where-Object { $_.Active -and $_.InstanceName -ceq $request.monitor_id })
    if ($active.Count -ne 1) { throw 'STALE_DEVICE: Approved monitor is no longer active' }
    if ($active[0].CurrentBrightness -ne $request.previous_brightness) { throw 'STALE_STATE: Brightness changed after preview' }
    $monitor = @(Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightnessMethods | Where-Object { $_.InstanceName -ceq $request.monitor_id })
    if ($monitor.Count -ne 1) { throw 'UNSUPPORTED_HARDWARE: No unique brightness setter' }
    $class = New-Object System.Management.ManagementClass('root\wmi:WmiMonitorBrightnessMethods')
    $native = @($class.GetInstances() | Where-Object { $_.InstanceName -ceq $request.monitor_id })
    if ($native.Count -ne 1) { throw 'UNSUPPORTED_HARDWARE: No unique native brightness setter' }
    $device = $native[0]
    $parameters = $device.GetMethodParameters('WmiSetBrightness')
    $parameters['Timeout'] = [uint32]1
    $parameters['Brightness'] = [byte]$request.brightness
    $result = $device.InvokeMethod('WmiSetBrightness', $parameters, $null)
    if ($null -ne $result.ReturnValue -and $result.ReturnValue -ne 0) { throw "WmiSetBrightness returned $($result.ReturnValue)" }
    @{ok=$true} | ConvertTo-Json -Compress
} catch {
    @{ok=$false;error=$_.Exception.Message} | ConvertTo-Json -Compress
    exit 1
}
"""


def powershell_binary():
    return Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"


class NativeControlError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class StrictInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class AudioChange(StrictInput):
    volume: int | None = Field(default=None, ge=0, le=100)
    muted: bool | None = None

    @model_validator(mode="after")
    def change_required(self):
        if (self.volume is None) == (self.muted is None):
            raise ValueError("Specify exactly one of volume or muted")
        return self


class BrightnessChange(StrictInput):
    brightness: int = Field(ge=0, le=100)
    monitor_id: str | None = Field(default=None, min_length=1, max_length=300)


class AudioApproval(AudioChange):
    device_id: str = Field(min_length=1, max_length=300)
    previous_volume: float = Field(ge=0, le=100)
    previous_muted: bool


class BrightnessApproval(BrightnessChange):
    monitor_id: str = Field(min_length=1, max_length=300)
    previous_brightness: int = Field(ge=0, le=100)


class Approval(StrictInput):
    id: str = Field(min_length=1, max_length=128)
    session: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")


class NativeRequest(StrictInput):
    operation: Literal["prepare", "execute"]
    action: Literal["configure_audio", "configure_brightness"]
    args: dict
    approval: Approval | None = None


def native_dependencies(kind):
    from zohra.services.tool_execution.registry import CapabilityState
    if platform.system() != "Windows":
        return CapabilityState.UNSUPPORTED, "Requires a native Windows user session"
    modules = ("pycaw", "comtypes") if kind == "audio" else ("win32com", "pythoncom")
    missing = [name for name in modules if importlib.util.find_spec(name) is None]
    if missing:
        return CapabilityState.DEPENDENCY_MISSING, "Missing: " + ", ".join(missing)
    if kind == "display" and not powershell_binary().is_file():
        return CapabilityState.DEPENDENCY_MISSING, "Windows PowerShell CIM adapter missing"
    return CapabilityState.AVAILABLE, "Native adapter installed; device support and access checked on use"


def native_fault(kind, store=None):
    with (store or CapabilityStore()).session() as db:
        db.execute("CREATE TABLE IF NOT EXISTS native_faults(kind TEXT PRIMARY KEY, message TEXT NOT NULL)")
        row = db.execute("SELECT message FROM native_faults WHERE kind=?", (kind,)).fetchone()
        return row["message"] if row else None


def record_native_fault(kind, message, store=None):
    with (store or CapabilityStore()).session() as db:
        db.execute("CREATE TABLE IF NOT EXISTS native_faults(kind TEXT PRIMARY KEY, message TEXT NOT NULL)")
        db.execute("INSERT OR REPLACE INTO native_faults VALUES(?,?)", (kind, message))


def native_control_availability(kind):
    from zohra.services.tool_execution.registry import CapabilityState
    state, reason = native_dependencies(kind)
    if state == CapabilityState.AVAILABLE:
        fault = native_fault(kind)
        if fault:
            return CapabilityState.EXECUTION_FAILED, fault
    return state, reason


def require_healthy_control(kind, store=None):
    fault = native_fault(kind, store)
    if fault:
        raise NativeControlError("HARDWARE_UNHEALTHY", fault)


def require_windows():
    if platform.system() != "Windows":
        raise NativeControlError("UNSUPPORTED_OS", "Native Windows user session required")


class CoreAudio:
    @contextmanager
    def endpoint(self):
        require_windows()
        import comtypes
        from pycaw.pycaw import AudioUtilities
        comtypes.CoInitialize()
        device = None
        try:
            device = AudioUtilities.GetSpeakers()
            if device is None:
                raise NativeControlError("DEVICE_UNAVAILABLE", "No default multimedia audio output")
            yield device
        finally:
            device = None
            comtypes.CoUninitialize()

    def snapshot(self):
        with self.endpoint() as device:
            volume = device.EndpointVolume
            return {"device_id": str(device.id), "device_name": str(device.FriendlyName),
                    "volume": round(float(volume.GetMasterVolumeLevelScalar()) * 100, 3),
                    "muted": bool(volume.GetMute())}

    def apply(self, args):
        with self.endpoint() as device:
            volume = device.EndpointVolume
            if str(device.id) != args.device_id:
                raise NativeControlError("STALE_DEVICE", "Default audio output changed; request a new approval")
            if abs(float(volume.GetMasterVolumeLevelScalar()) * 100 - args.previous_volume) > .6 or bool(volume.GetMute()) != args.previous_muted:
                raise NativeControlError("STALE_STATE", "Audio settings changed after the preview; request a new approval")
            if args.volume is not None:
                volume.SetMasterVolumeLevelScalar(args.volume / 100, None)
            else:
                volume.SetMute(int(args.muted), None)


class WmiBrightness:
    @contextmanager
    def service(self):
        require_windows()
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        service = None
        try:
            service = win32com.client.Dispatch("WbemScripting.SWbemLocator").ConnectServer(".", r"root\wmi")
            yield service
        finally:
            service = None
            pythoncom.CoUninitialize()

    def snapshot(self):
        with self.service() as service:
            monitors = [{"monitor_id": str(item.InstanceName), "brightness": int(item.CurrentBrightness),
                         "levels": [int(value) for value in item.Level]}
                        for item in service.ExecQuery("SELECT * FROM WmiMonitorBrightness WHERE Active=True")]
        if not monitors:
            raise NativeControlError("UNSUPPORTED_HARDWARE", "No active WMI brightness monitor; external-monitor DDC/CI is not integrated")
        return monitors

    def apply(self, args):
        require_windows()
        # Named native arguments avoid this host's SWbem setter mismatch. Approved
        # values are JSON stdin, never interpolated into executable commands.
        result = subprocess.run([str(powershell_binary()), "-NoProfile", "-NonInteractive", "-Command", BRIGHTNESS_COMMAND],
            input=json.dumps(args.model_dump()), text=True, capture_output=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            output = json.loads(result.stdout.strip())
        except (ValueError, TypeError):
            raise NativeControlError("NATIVE_ERROR", f"Brightness adapter returned invalid output: {result.stderr.strip()[:1000]}")
        if result.returncode != 0 or output.get("ok") is not True:
            raise NativeControlError("NATIVE_ERROR", str(output.get("error") or result.stderr.strip() or "Brightness adapter failed"))


def audio_status(backend=None):
    return {**(backend or CoreAudio()).snapshot(), "source": "Windows Core Audio default multimedia endpoint",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "limitations": "Master volume/mute only. App volumes and default-output switching are not implemented."}


def display_status(backend=None):
    return {"monitors": (backend or WmiBrightness()).snapshot(), "source": "Windows WMI active monitor brightness",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "limitations": "WMI-compatible displays only; external-monitor DDC/CI and resolution controls are not implemented."}


def prepare_control(action, raw_args, audio=None, display=None):
    if action == "configure_audio":
        requested = AudioChange.model_validate(raw_args)
        require_healthy_control("audio")
        before = (audio or CoreAudio()).snapshot()
        args = AudioApproval(**requested.model_dump(), device_id=before["device_id"],
                             previous_volume=float(before["volume"]), previous_muted=before["muted"])
        description = (f"Set master volume to {args.volume}%" if args.volume is not None else
                       f"{'Mute' if args.muted else 'Unmute'} master audio") + f" on {before['device_name']}."
        consequence = f"Changes master audio on the current output. Current volume is {before['volume']}%, muted: {before['muted']}. No output-device switch, application volume or trading setting changes."
    elif action == "configure_brightness":
        requested = BrightnessChange.model_validate(raw_args)
        require_healthy_control("display")
        monitors = (display or WmiBrightness()).snapshot()
        matches = [item for item in monitors if requested.monitor_id is None or item["monitor_id"] == requested.monitor_id]
        if len(matches) != 1:
            raise NativeControlError("AMBIGUOUS_DEVICE", "Choose an exact active monitor_id from display status")
        before = matches[0]
        args = BrightnessApproval(brightness=requested.brightness, monitor_id=before["monitor_id"], previous_brightness=before["brightness"])
        description = f"Set brightness to {args.brightness}% on monitor {args.monitor_id}."
        consequence = f"Changes display brightness from {args.previous_brightness}%. Low values may make the screen hard to see. Other display settings remain unchanged."
    else:
        raise NativeControlError("PERMISSION_DENIED", "Unregistered native action")
    return {"args": args.model_dump(), "description": description, "consequence": consequence}


def claim_approval(action, args, approval, store):
    approval = Approval.model_validate(approval)
    tool_id = "windows.audio" if action == "configure_audio" else "windows.display"
    with store.session() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM confirmations WHERE id=? AND session=?", (approval.id, approval.session)).fetchone()
        enabled = db.execute("SELECT enabled FROM tool_controls WHERE tool_id=?", (tool_id,)).fetchone()
        if enabled is not None and not enabled["enabled"]:
            raise NativeControlError("TOOL_DISABLED", "Native capability was revoked")
        if not row or row["status"] != "executing" or row["action"] != action or row["expires"] < time.time() * 1000 or json.loads(row["args"]) != args:
            raise NativeControlError("STALE_CONFIRMATION", "Native action lacks an exact current bridge approval")
        db.execute("CREATE TABLE IF NOT EXISTS native_claims(confirmation_id TEXT PRIMARY KEY, created TEXT DEFAULT CURRENT_TIMESTAMP)")
        if db.execute("SELECT 1 FROM native_claims WHERE confirmation_id=?", (approval.id,)).fetchone():
            raise NativeControlError("STALE_CONFIRMATION", "Native approval already consumed")
        db.execute("INSERT INTO native_claims(confirmation_id) VALUES(?)", (approval.id,))


def execute_control(action, raw_args, approval, store=None, audio=None, display=None):
    if approval is None:
        raise NativeControlError("CONFIRMATION_REQUIRED", "A separate confirmed bridge action is required")
    model = AudioApproval if action == "configure_audio" else BrightnessApproval if action == "configure_brightness" else None
    if model is None:
        raise NativeControlError("PERMISSION_DENIED", "Unregistered native action")
    args = model.model_validate(raw_args)
    store = store or CapabilityStore()
    kind = "audio" if action == "configure_audio" else "display"
    require_healthy_control(kind, store)
    claim_approval(action, args.model_dump(), approval, store)
    if action == "configure_audio":
        backend = audio or CoreAudio()
        backend.apply(args)
        after = backend.snapshot()
        verified = after["device_id"] == args.device_id and (abs(after["volume"] - args.volume) <= .6 if args.volume is not None else after["muted"] == args.muted)
        # A volume change must never implicitly unmute, and mute must not alter volume.
        verified = verified and (after["muted"] == args.previous_muted if args.volume is not None else abs(after["volume"] - args.previous_volume) <= .6)
    else:
        backend = display or WmiBrightness()
        backend.apply(args)
        deadline = time.monotonic() + 2
        while True:
            after = next((item for item in backend.snapshot() if item["monitor_id"] == args.monitor_id), None)
            verified = after is not None and after["brightness"] == args.brightness
            if verified or after is None or time.monotonic() >= deadline:
                break
            time.sleep(.15)
    if not verified:
        message = f"Windows setting did not match the approved value on read-back: {json.dumps(after)}. Further {kind} writes blocked until operator diagnosis/reset. No automatic retry was attempted."
        record_native_fault(kind, message, store)
        raise NativeControlError("VERIFICATION_FAILED", message)
    return {"verified": True, "after": after, "source": "native Windows setting read-back",
            "observed_at": datetime.now(timezone.utc).isoformat()}
