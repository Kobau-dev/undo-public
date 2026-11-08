"""Prepare the raw takes for the edit.

    python3 film/tools/takes.py mail_a=mail_a_1 crm=crm_1 blender=blender_1 mail_b=mail_b_1

Crops the black notch band (33 points) from ~/Movies/Undo demo/raw2/<take>.mov and writes film/public/takes/<video>.mp4, seekable.
Reads what happened and when from <take>.marks.json and Undo's log, and merges it into film/src/takes.json: the timeline is built
from these times, so a new take only needs this script to be run again.
"""
import json
import pathlib
import re
import subprocess
import sys
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parents[2]
RAW = pathlib.Path.home() / "Movies/Undo demo/raw2"
OUT = ROOT / "film/public/takes"
DATA = ROOT / "film/src/takes.json"
KEYS = {"cmd+z": "⌘Z", "cmd+c": "⌘C", "cmd+v": "⌘V", "cmd+shift+z": "⇧⌘Z", "shift+cmd+z": "⇧⌘Z"}


def steps_of(log: pathlib.Path, t0: float) -> tuple[list[dict], float | None]:
    """Undo's action lines with their time in the recording, and when it took over the screen. The log prints a clock time only
    when the second changes: the lines of one second are spread evenly across it."""
    day = datetime.fromtimestamp(t0).date()
    clock = None
    out = []
    act = None
    for line in log.read_text(errors="replace").splitlines():
        m = re.match(r"(\d\d:\d\d:\d\d) ", line)
        if m:
            clock = datetime.combine(day, datetime.strptime(m.group(1), "%H:%M:%S").time()).timestamp()
        if clock and act is None and "input locked" in line:
            act = round(clock - t0, 2)
        s = re.search(r"step (\d+\.\d+): (.+?)\s*$", line)
        if s and clock:
            out.append({"t": round(clock - t0, 2), "step": s.group(1), "what": s.group(2)})
    for sec in {s["t"] for s in out}:
        same = [s for s in out if s["t"] == sec]
        for i, s in enumerate(same):
            s["t"] = round(sec + i / len(same), 2)
    return out, act


def main() -> None:
    data = json.loads(DATA.read_text()) if DATA.exists() else {}
    for arg in sys.argv[1:]:
        video, take = arg.split("=")
        mov = RAW / f"{take}.mov"
        raw = json.loads((RAW / f"{take}.marks.json").read_text())
        t0 = raw.pop("t0_epoch", None) or mov.stat().st_birthtime
        clicks = raw.pop("clicks", [])
        steps, act = steps_of(RAW / f"{take}.log", t0)
        keys = []
        for s in steps:
            k = re.match(r"key (\S+)", s["what"])
            if k and k.group(1) in KEYS:
                keys.append({"t": s["t"], "label": KEYS[k.group(1)]})
        events = {}
        villa = RAW / f"{take}.villa.log"
        if villa.exists():  # the Blender scene logs each modelling step with its time
            for line in villa.read_text().splitlines():
                v = re.match(r"VILLA (\d+\.\d+) (.+)", line)
                if v:
                    events.setdefault(v.group(2), round(float(v.group(1)) - t0, 2))
        data[video] = {"take": take, "t0": t0, "clock": datetime.fromtimestamp(t0).strftime("%H:%M"), "marks": raw, "clicks": clicks, "steps": steps, "keys": keys, "events": events, "act": act,
                       "duration": float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mov)]).strip())}
        OUT.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mov), "-an", "-vf", "crop=2940:1846:0:66", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-g", "15",
                        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(OUT / f"{video}.mp4")], check=True)
        print(video, take, data[video]["clock"], {k: v for k, v in raw.items()}, len(steps), "steps")
    DATA.write_text(json.dumps(data, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
