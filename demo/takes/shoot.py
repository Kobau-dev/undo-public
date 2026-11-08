"""Shoot one demo take for the film: real pointer, real Undo, real voice flow.

An ElevenLabs line (film/public/vo/<line>.mp3) goes straight into Undo's audio input in real time (see run_undo.py), and Undo
transcribes it live like any voice. With --mic it is played through the MacBook speakers into the MacBook microphone instead (needs
the speakers on, and a quiet room). Nothing else in the run is scripted on Undo's side.

    <python> demo/takes/shoot.py check                 # permissions, devices, keys: nothing audible, nothing on screen
    <python> demo/takes/shoot.py mictest               # plays one line and measures it at the microphone
    <python> demo/takes/shoot.py mail_a|crm|blender|mail_b [--dry] [--name 1] [--mic] [--typed] [--separate]

Run in that order: all the takes write to one history (raw2/history_data), as on a real day, so mail_b really finds the email
read in mail_a, several minutes and two other takes earlier. Everything is in English (UNDO_LANGUAGES=en).
--dry prepares the apps and saves a screenshot instead of recording. Use the Python of the checkout holding the keys
(UNDO_KEYS_ENV, default ~/dev/hackathon/undo/.env). The code that runs is this checkout's.
Output: ~/Movies/Undo demo/raw2/<take>_<name>.mov, .marks.json and .log. Typing stops if another app takes the focus.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import signal
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import Quartz
import sounddevice as sd
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
OUT = Path.home() / "Movies/Undo demo/raw2"
HISTORY = OUT / "history_data"
VO = ROOT / "film/public/vo"
PY = sys.executable
KEYS_ENV = Path(os.environ.get("UNDO_KEYS_ENV", Path.home() / "dev/hackathon/undo/.env"))
SPEAKERS = os.environ.get("UNDO_TAKE_SPEAKERS", "Haut-parleurs MacBook Air")
MIC = os.environ.get("UNDO_TAKE_MIC", "Micro MacBook Air")
SCREEN = os.environ.get("UNDO_TAKE_SCREEN", "Capture screen 0")
GAIN = float(os.environ.get("UNDO_TAKE_GAIN", "1.0"))
READ_SECONDS = float(os.environ.get("UNDO_TAKE_READ", "1.8"))  # the transcript stays on screen this long before Enter
BLENDER = os.environ.get("BLENDER", "/Applications/Blender.app/Contents/MacOS/Blender")

T0: float | None = None
MARKS: dict[str, float] = {}
CLICKS: list[float] = []  # seconds in the recording, for the click sounds of the edit
# The requests as text, for a take with --typed (nothing audible): same words as the spoken lines.
REQUESTS = {
    "bl_req": "No, no, no... I deleted the pool and the deck earlier, and I don't know how to get them back. Put them back, without losing anything I've done since.",
    "crm_req": "Oh no... the session expired and my visit report is gone. Put back what I'd filled in.",
    "mail_req": "In the description, explain that my order never arrived, with the order number, the date, the item, the amount and the package tracking from the email I read this morning.",
}


class Abort(Exception):
    pass


def mark(name: str) -> None:
    t = round(time.time() - T0, 2) if T0 else 0.0
    MARKS[name] = t
    print(f"MARK {name} {t}", flush=True)


# ---- input ------------------------------------------------------------------------------------------------------
def post(e) -> None:
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, e)


def pointer() -> tuple[float, float]:
    loc = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
    return loc.x, loc.y


def move(x: float, y: float, dur: float = 0.55) -> None:
    """Glide along a slight arc, the way a hand moves on a trackpad."""
    x0, y0 = pointer()
    dist = math.hypot(x - x0, y - y0)
    n = max(8, int(dur * 60))
    nx, ny = (-(y - y0) / dist, (x - x0) / dist) if dist else (0, 0)
    bow = min(30, dist * 0.06)
    for i in range(1, n + 1):
        u = i / n
        u = 4 * u ** 3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2
        b = math.sin(math.pi * u) * bow
        e = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, (x0 + (x - x0) * u + nx * b, y0 + (y - y0) * u + ny * b), 0)
        Quartz.CGEventSetFlags(e, 0)
        post(e)
        time.sleep(dur / n)


def click(x: float, y: float, dur: float = 0.55) -> None:
    move(x, y, dur)
    time.sleep(0.12)
    if T0:
        CLICKS.append(round(time.time() - T0, 2))
    for kind in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
        e = Quartz.CGEventCreateMouseEvent(None, kind, (x, y), Quartz.kCGMouseButtonLeft)
        Quartz.CGEventSetFlags(e, 0)
        post(e)
        time.sleep(0.04)


def scroll(points: int, dur: float = 0.6) -> None:
    """Smooth page scroll by `points` (positive = down)."""
    n = max(1, abs(points) // 6)
    step = int(points / n)
    for _ in range(n):
        post(Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitPixel, 1, -step))
        time.sleep(dur / n)


def key(code: int, flags: int = 0) -> None:
    for down in (True, False):
        e = Quartz.CGEventCreateKeyboardEvent(None, code, down)
        Quartz.CGEventSetFlags(e, flags)
        post(e)
        time.sleep(0.03)


def double_shift() -> None:
    for code in (56, 59, 58, 55):  # release shift/ctrl/opt/cmd first
        e = Quartz.CGEventCreateKeyboardEvent(None, code, False)
        Quartz.CGEventSetType(e, Quartz.kCGEventFlagsChanged)
        Quartz.CGEventSetFlags(e, 0)
        post(e)
    time.sleep(0.3)
    for _ in range(2):
        for down in (True, False):
            e = Quartz.CGEventCreateKeyboardEvent(None, 56, down)
            Quartz.CGEventSetFlags(e, Quartz.kCGEventFlagMaskShift if down else 0)
            Quartz.CGEventSetType(e, Quartz.kCGEventFlagsChanged)
            post(e)
            time.sleep(0.07)


def front() -> tuple[str, int, dict]:
    """Owner of the frontmost normal window (NSWorkspace goes stale without a run loop)."""
    opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    for w in Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID):
        if w.get("kCGWindowLayer") == 0 and w.get("kCGWindowAlpha", 1) > 0:
            return str(w.get("kCGWindowOwnerName")), int(w.get("kCGWindowOwnerPID")), dict(w.get("kCGWindowBounds") or {})
    return "", 0, {}


def require_front(want: str | int) -> None:
    name, pid, _ = front()
    if pid != want if isinstance(want, int) else want not in name:
        raise Abort(f"focus moved to {name} (expected {want}): stopping before typing anywhere else")


def type_text(text: str, want: str | int, per_char: float = 0.03) -> None:
    for ch in text:
        require_front(want)
        for down in (True, False):
            e = Quartz.CGEventCreateKeyboardEvent(None, 0, down)
            Quartz.CGEventKeyboardSetUnicodeString(e, len(ch.encode("utf-16-le")) // 2, ch)
            Quartz.CGEventSetFlags(e, 0)
            post(e)
        time.sleep(per_char + random.uniform(0, 0.025) + (0.1 if ch in ".,;:" else 0))


def activate(app: str) -> None:
    subprocess.run(["osascript", "-e", f'tell application "{app}" to activate'], check=True)


def fullscreen(process: str) -> None:
    """Native full screen through the window's accessibility attribute: a keyboard shortcut depends on the app. `process` is
    an AppleScript reference, e.g. 'process "Blender"' or 'first process whose unix id is 123'."""
    subprocess.run(["osascript", "-e", f'tell application "System Events" to tell ({process}) to set value of attribute "AXFullScreen" of window 1 to true'], check=True)
    time.sleep(2.5)


def activate_pid(pid: int) -> None:
    subprocess.run(["osascript", "-e", f'tell application "System Events" to set frontmost of (first process whose unix id is {pid}) to true'], check=True)


# ---- voice ------------------------------------------------------------------------------------------------------
def decode(line: str) -> np.ndarray:
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(VO / f"{line}.mp3"), "-f", "f32le", "-ac", "2", "-ar", "44100", "-"])
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2)


def say(line: str) -> None:
    data = np.clip(decode(line) * GAIN, -1, 1)
    mark("voice_start")
    sd.play(data, 44100, device=SPEAKERS, blocking=True)
    mark("voice_end")


def feed(line: str, control: Path) -> None:
    """The line, at a normal speaking level, straight into Undo's audio input."""
    raw = OUT / f"{line}.f32"
    pcm = np.frombuffer(subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(VO / f"{line}.mp3"), "-f", "f32le", "-ac", "1", "-ar", "16000", "-"]), dtype=np.float32)
    level = float(np.sqrt(np.mean(np.square(pcm))))
    (pcm * (0.07 / max(level, 1e-4))).clip(-1, 1).astype(np.float32).tofile(raw)
    mark("voice_start")
    control.write_text(str(raw))
    time.sleep(len(pcm) / 16000)
    mark("voice_end")


def mictest(line: str) -> None:
    """Play a line and measure it at the microphone. Undo's silence threshold is an RMS of 0.012."""
    data = np.clip(decode(line) * GAIN, -1, 1)
    sr = 16000
    quiet = sd.rec(int(1.5 * sr), samplerate=sr, channels=1, dtype="float32", device=MIC, blocking=True)[:, 0]
    chunks: list[np.ndarray] = []  # its own stream: sd.play would stop an sd.rec running at the same time
    with sd.InputStream(samplerate=sr, channels=1, dtype="float32", device=MIC, callback=lambda d, _f, _t, _s: chunks.append(d[:, 0].copy())):
        sd.play(data, 44100, device=SPEAKERS, blocking=True)
        time.sleep(0.5)
    rec = np.concatenate(chunks)
    rms = lambda x: float(np.sqrt(np.mean(np.square(x))))
    win = [rms(rec[i:i + 1024]) for i in range(0, len(rec) - 1024, 1024)]
    print(json.dumps({"room_rms": round(rms(quiet), 4), "voice_rms": round(rms(rec), 4), "voice_p90": round(float(np.percentile(win, 90)), 4),
                      "clipped": bool(np.max(np.abs(rec)) > 0.99), "silence_threshold": 0.012}))
    if rms(quiet) > 0.012:
        print("ROOM TOO LOUD for silence detection: the take will stop the recording with the hotkey instead")


# ---- the take ---------------------------------------------------------------------------------------------------
class Take:
    def __init__(self, name: str, tag: str, dry: bool, recipe: str | None = None, step_delay: str | None = None, typed: bool = False, separate: bool = False, mic: bool = False):
        self.name, self.dry, self.typed, self.mic = name, dry, typed, mic
        self.separate = dry or separate  # a rehearsal keeps its own history, away from the real day
        OUT.mkdir(parents=True, exist_ok=True)
        self.base = OUT / f"{name}_{tag}"
        self.log = self.base.with_suffix(".log")
        self.video = self.base.with_suffix(".mov")
        self.recipe, self.step_delay = recipe, step_delay
        self.undo: subprocess.Popen | None = None
        self.ff: subprocess.Popen | None = None
        self.extra: list[subprocess.Popen] = []

    def start_undo(self) -> None:
        env = {**os.environ, **{k: v for k, v in dotenv_values(KEYS_ENV).items() if v and k in ("H_API_KEY", "GLADIA_API_KEY")}}
        env.update(UNDO_DATA_DIR=str(self.base) + "_data" if self.separate else str(HISTORY), UNDO_LANGUAGES="en", UNDO_HUD_CAPTURABLE="1", UNDO_VOICE="1", UNDO_LIVE_STT="1", PYTHONPATH=str(ROOT))
        if self.recipe:
            env["UNDO_RECIPE"] = self.recipe
        if self.step_delay:
            env["UNDO_STEP_DELAY"] = self.step_delay
        self.feed = self.base.with_suffix(".feed")
        self.feed.unlink(missing_ok=True)
        if not self.mic:
            env["UNDO_TAKE_FEED"] = str(self.feed)
        self.undo = subprocess.Popen([PY, str(ROOT / "demo/takes/run_undo.py")], cwd=ROOT, env=env, stdout=self.log.open("w"), stderr=subprocess.STDOUT)
        time.sleep(6)
        if self.undo.poll() is not None:
            raise Abort(f"Undo exited at start, see {self.log}")

    def start_rec(self) -> None:
        global T0
        if self.dry:
            shot = self.base.with_suffix(".dry.png")
            subprocess.run(["screencapture", "-x", str(shot)], check=True)
            print("DRY screenshot", shot, "front", front()[0], front()[2], "pointer", pointer())
            raise Abort("dry run stops here")
        self.ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "avfoundation", "-capture_cursor", "1", "-capture_mouse_clicks", "0",
                                    "-framerate", "30", "-i", f"{SCREEN}:none", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "16",
                                    "-pix_fmt", "yuv420p", str(self.video)], stdin=subprocess.DEVNULL)
        T0 = time.time()
        time.sleep(1.2)
        if self.ff.poll() is not None:
            raise Abort("screen capture did not start")
        mark("rec_start")

    def log_has(self, text: str, since: int = 0) -> bool:
        return text in self.log.read_text(errors="replace")[since:]

    def ask(self, line: str, want: str | int) -> None:
        require_front(want)
        since = self.log.stat().st_size
        double_shift()
        mark("hotkey")
        time.sleep(1.4)
        if self.typed:
            mark("voice_start")
            type_text(REQUESTS[line], want, 0.02)
            mark("voice_end")
            time.sleep(READ_SECONDS)
            key(36)  # Return
            mark("request_sent")
            return
        if self.mic:
            say(line)
        else:
            feed(line, self.feed)
        for _ in range(30):  # two seconds of silence end the recording by themselves
            time.sleep(0.1)
            if self.log_has("recorded ", since) or self.log_has("no speech", since):
                break
        else:  # a noisy room never goes quiet: a double Shift ends the recording, as it does for a person
            double_shift()
            mark("stop_tap")
        for _ in range(150):  # the transcript lands in the text box, and only Enter sends it
            time.sleep(0.1)
            if self.log_has("request in the text box", since):
                break
        else:
            raise Abort("the transcript never reached the text box")
        mark("in_the_box")
        time.sleep(READ_SECONDS)
        key(36)  # Return
        mark("request_sent")

    def wait_done(self, timeout: float = 170) -> None:
        since = 0
        start = time.time()
        while time.time() - start < timeout:
            if self.log_has("executor finished", since):
                mark("done")
                return
            if self.undo and self.undo.poll() is not None:
                raise Abort("Undo exited during the take")
            time.sleep(0.25)
        raise Abort("no 'executor finished' in time")

    def stop(self) -> None:
        if self.ff and self.ff.poll() is None:
            self.ff.send_signal(signal.SIGINT)
            self.ff.wait(timeout=20)
        for p in [self.undo, *self.extra]:
            if p and p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    p.kill()
        self.base.with_suffix(".marks.json").write_text(json.dumps({**MARKS, "t0_epoch": T0, "clicks": CLICKS}, indent=1))
        print("saved", self.video if self.video.exists() else "(no video)", MARKS)
        interesting = ("live transcript", "recorded ", "analysis ok", "executor finished", "step ", "hotkey", "ERROR", "Traceback", "voice unavailable")
        for ln in self.log.read_text(errors="replace").splitlines():
            if any(k in ln for k in interesting):
                print(ln[:190])


# In every take the app is in front before Undo starts: the history must not hold what was on screen before the take.
# ---- 1. Blender ----------------------------------------------------------------------------------------------------
def blender(t: Take) -> None:
    d = ROOT / "demo/blender"
    out = d / "out"
    out.mkdir(exist_ok=True)
    blend = d / "villa_martin.blend"
    if not blend.exists():
        expr = f"import bpy\nfor o in list(bpy.data.objects): bpy.data.objects.remove(o)\nbpy.ops.wm.save_as_mainfile(filepath='{blend}')"
        subprocess.run([BLENDER, "-b", "--factory-startup", "--python-expr", expr], capture_output=True)
    subprocess.run(["pkill", "-f", "Blender --factory-startup"])
    time.sleep(1.5)
    villa_log = out / "villa.log"
    villa_log.unlink(missing_ok=True)
    env = {**os.environ, "VILLA_LOG": str(villa_log), "VILLA_DELAY": "21"}
    t.extra.append(subprocess.Popen([BLENDER, "--factory-startup", str(blend), "--python", str(d / "villa_demo.py")], env=env,
                                    stdout=(out / "blender.log").open("w"), stderr=subprocess.STDOUT))
    time.sleep(5)
    activate("Blender")
    time.sleep(1)
    fullscreen('process "Blender"')
    t.start_undo()
    move(1300, 820, 0.5)
    t.start_rec()
    for _ in range(60):
        if villa_log.exists() and "done" in villa_log.read_text():
            break
        time.sleep(1)
    mark("villa_done")
    time.sleep(3.5)
    activate("Blender")
    time.sleep(0.5)
    (t.base.with_suffix(".villa.log")).write_text(villa_log.read_text())  # when each modelling step happened, for the edit
    t.ask("bl_req", "Blender")
    t.wait_done()
    time.sleep(5)


# ---- 2. CRM --------------------------------------------------------------------------------------------------------
CRM_REPORT = ("Visit to Dr Marchand's practice, a 20-minute conversation early in the afternoon. Context: a young urban patient base, with a "
              "growing share of type 2 diabetes and poorly controlled hypertension. On Tensiora 5/10 mg: presented the fixed-dose combination and "
              "the simpler dosing, one tablet a day. The adherence argument landed well, especially for older patients on several medications. "
              "Asked for long-term tolerance data (edema, orthostatic hypotension) before prescribing it more widely. On Glycalm XR 1000 mg: the "
              "extended-release form is of interest to limit the digestive issues seen with standard metformin. Two patients recently stopped "
              "because of digestive intolerance, so this looks like a credible option. Question about reimbursement and its place as a second-line "
              "treatment. Friendly meeting, ran a few minutes over schedule. Cautious but clearly interested: nothing is settled, we need to come "
              "back with the requested material.")
CRM_NEEDS = ("Needs: 12-month Tensiora tolerance data, Glycalm XR samples, clarity on reimbursement. Objections: cost for patients without "
             "supplementary insurance; wary of fixed-dose combinations (\"no dosing flexibility\").")
CMD, CTRL, SHIFT = Quartz.kCGEventFlagMaskCommand, Quartz.kCGEventFlagMaskControl, Quartz.kCGEventFlagMaskShift


def crm(t: Take) -> None:
    app = subprocess.Popen([PY, "-m", "demo.crm_app", "--contact", "marchand", "--new-report", "--session-timeout", "0", "--theme", "dark"],
                           cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT)}, stdout=t.base.with_suffix(".crm.log").open("w"), stderr=subprocess.STDOUT)
    t.extra.append(app)
    time.sleep(4)
    activate_pid(app.pid)
    time.sleep(1)
    fullscreen(f"first process whose unix id is {app.pid}")
    t.start_undo()
    move(735, 700, 0.4)
    t.start_rec()
    time.sleep(1)
    me = app.pid
    for (x, y), text, speed in (
        ((1211, 259), "12:45", 0.09), ((1321, 259), "20 min", 0.09),
        ((316, 328), None, 0), ((1146, 321), "Prescription follow-up", 0.04),
        ((468, 544), CRM_REPORT, 0.012), ((468, 722), CRM_NEEDS, 0.012),
        ((996, 410), None, 0), ((996, 428), None, 0),
        ((1119, 534), "Tensiora and Glycalm XR dosing sheets, GLP-2 study summary", 0.02),
        ((1119, 657), "Send the 12-month tolerance study and deliver Glycalm XR samples", 0.02),
        ((1039, 717), "01/12/2026", 0.08),
    ):
        require_front(me)
        click(x, y)
        time.sleep(0.25)
        if text:
            type_text(text, me, speed)
            time.sleep(0.25)
            if (x, y) == (1146, 321):
                key(48)  # Tab: closes the suggestions of the lookup field, or the next click would only close them
                time.sleep(0.2)
        else:
            time.sleep(0.5)
    mark("form_filled")
    time.sleep(1.5)
    key(14, CMD | SHIFT)  # the demo app's hidden command: the session expires now (a text field keeps Control+Shift+E for itself)
    mark("session_expired")
    time.sleep(3)
    click(735, 568)
    time.sleep(0.3)
    type_text("demo", me, 0.1)
    time.sleep(0.5)
    click(890, 646)
    mark("login")
    time.sleep(5)
    move(735, 560, 0.6)
    time.sleep(1.5)
    t.ask("crm_req", me)
    t.wait_done()
    time.sleep(5)


# ---- 3. Mail, then SignalConso later ---------------------------------------------------------------------------------
# Two separate recordings with real time between them. Prepared by hand first: Mail in English in full screen on the sample inbox
# (demo/mbox_en); the browser in full screen on the Description step of signal.conso.gouv.fr/en. Each app is
# already in front when the recording starts, so no slide between Spaces is ever on screen.
BROWSER = os.environ.get("UNDO_TAKE_BROWSER", "Brave Browser")
MAIL_ROW = (400, 855)  # the parcel email, the oldest of the list
READING = ((1180, 455), (1200, 485), (1130, 515), (1230, 545), (960, 624), (1000, 647))  # the pointer follows the order details while the email is read


def mail_a(t: Take) -> None:
    activate("Mail")
    time.sleep(2.5)
    fullscreen('process "Mail"')
    t.start_undo()
    move(620, 500, 0.5)
    t.start_rec()
    time.sleep(1.5)
    click(*MAIL_ROW, 0.9)
    mark("mail_open")
    time.sleep(1.5)
    for x, y in READING:
        move(x, y, 0.8)
        time.sleep(1.1)
    mark("read")
    time.sleep(2)


def mail_b(t: Take) -> None:
    activate(BROWSER)
    time.sleep(3)
    fullscreen(f'process "{BROWSER}"')
    move(735, 560, 0.3)
    scroll(-1500, 0.3)  # from the top of the page, for any retake
    t.start_undo()
    t.start_rec()
    time.sleep(1.5)
    scroll(DESCRIPTION_SCROLL)  # the field goes above Undo's bubble, so the bubble does not hide what gets written
    time.sleep(0.8)
    click(*DESCRIPTION)
    mark("description")
    time.sleep(2)
    t.ask("mail_req", BROWSER.split()[0])
    t.wait_done()
    time.sleep(6)


DESCRIPTION = (735, 565)
DESCRIPTION_SCROLL = 290


# ---- main -----------------------------------------------------------------------------------------------------------
def check() -> int:
    ok = True
    def line(name: str, good: bool, more: str = "") -> None:
        nonlocal ok
        ok = ok and good
        print(("ok  " if good else "FAIL"), name, more)
    from ApplicationServices import AXIsProcessTrusted
    line("accessibility", bool(AXIsProcessTrusted()))
    line("screen recording", bool(Quartz.CGPreflightScreenCaptureAccess()))
    line("post events", bool(Quartz.CGPreflightPostEventAccess()))
    names = [d["name"] for d in sd.query_devices()]
    line("microphone device", any(MIC in n for n in names), MIC)
    line("speakers device", any(SPEAKERS in n for n in names), SPEAKERS)
    screens = subprocess.run(["ffmpeg", "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""], capture_output=True, text=True).stderr
    line("screen device", SCREEN in screens, SCREEN)
    keys = dotenv_values(KEYS_ENV)
    line("H key", bool(keys.get("H_API_KEY")), str(KEYS_ENV))
    line("Gladia key", bool(keys.get("GLADIA_API_KEY")))
    for mod in ("PySide6", "pyautogui", "undo", "demo.crm_app.pages"):
        try:
            __import__(mod)
            line(f"import {mod}", True)
        except Exception as exc:
            line(f"import {mod}", False, repr(exc))
    for name in ("bl_req", "crm_req", "mail_req"):
        line(f"voice line {name}", (VO / f"{name}.mp3").exists())
    line("blender app", Path(BLENDER).exists())
    others = subprocess.run(["pgrep", "-fl", "undo run|run_undo"], capture_output=True, text=True).stdout.strip()
    line("no other Undo running", not others, others.replace("\n", " | ")[:200])
    return 0 if ok else 1


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("what", choices=["check", "mictest", "mail_a", "mail_b", "crm", "blender"])
    p.add_argument("--dry", action="store_true")
    p.add_argument("--name", default="1")
    p.add_argument("--line", default="crm_req")
    p.add_argument("--typed", action="store_true", help="type the request instead of speaking it")
    p.add_argument("--mic", action="store_true", help="play the voice through the speakers into the microphone")
    p.add_argument("--separate", action="store_true", help="rehearsal: keep its own history, not the shared one")
    a = p.parse_args()
    if a.what == "check":
        return check()
    if a.what == "mictest":
        mictest(a.line)
        return 0
    recipe = {"blender": str(ROOT / "demo/blender/recipe_villa.md")}.get(a.what)
    step = {"blender": "0.3"}.get(a.what)
    t = Take(a.what, a.name, a.dry, recipe, step, a.typed, a.separate, a.mic)
    try:
        {"mail_a": mail_a, "mail_b": mail_b, "crm": crm, "blender": blender}[a.what](t)
        return 0
    except Abort as exc:
        print("STOPPED:", exc)
        return 3
    finally:
        t.stop()
        subprocess.run(["osascript", "-e", 'tell application "Claude" to activate'])


if __name__ == "__main__":
    raise SystemExit(main())
