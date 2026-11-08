"""Generate the English voice-over with ElevenLabs (key in ../.env: ELEVENLABS_API_KEY).

Two voices: the narrator (calm, informative) and the person using Undo (stressed in Blender and the CRM, calm in the mail
example). Audio tags like [nervous] only work on eleven_v3: they shape the delivery and are not spoken.

Usage: python3 film/tools/vo.py [line_id ...]   (no id = all missing lines; ids given = regenerate them)
Writes film/public/vo/<id>.mp3 and film/src/vo.json (durations in seconds).
"""
import json
import pathlib
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "film/public/vo"
NARRATOR = "cjVigY5qzO86Huf0OWal"  # Eric: smooth, trustworthy (American)
PERSON = "EXAVITQu4vr4xnSDxMaL"  # Sarah: young, professional (American); the CRM user on screen is Camille

VOICES = {
    NARRATOR: {"model_id": "eleven_multilingual_v2",
               "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "style": 0.15, "use_speaker_boost": True, "speed": 0.93}},
    PERSON: {"model_id": "eleven_v3", "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
}

LINES = {
    "intro": (NARRATOR, "Command-Z goes back one step at a time, inside one app. "
                        "Undo keeps a history of what happened on your Mac, and can act on it. Three real takes."),
    # Blender: a tool you don't know well
    "bl1": (NARRATOR, "Say you don't really know Blender. You delete the pool and the deck by mistake, and you keep working."),
    "bl2": (NARRATOR, "Command-Z would bring them back, but erase everything since. An expert knows a way around that. Most of us don't."),
    "bl_req": (PERSON, "[nervous] No, no, no... [sighs] I deleted the pool and the deck earlier, and I don't know how to get them back. "
                       "[worried] Put them back, without losing anything I've done since."),
    "bl3": (NARRATOR, "Undo does it for you. It steps back, copies the pool and the deck, returns to the present, and pastes them in. "
                      "Nothing is lost."),
    # CRM: lost work
    "crm1": (NARRATOR, "A visit report, filled in. The session expires, and the form comes back empty."),
    "crm_req": (PERSON, "[frustrated] Oh no... the session expired and my visit report is gone. [sighs] Put back what I'd filled in."),
    "crm2": (NARRATOR, "Undo finds the last state of the form in its history, and fills in every field. It stops before saving."),
    # Mail: not even a mistake, something seen earlier
    "mail1": (NARRATOR, "It doesn't have to be a mistake. This morning, you checked a delivery email. "
                        "Now there's a complaint to file, and the details are back in that email."),
    "mail_req": (PERSON, "In the description, explain that my order never arrived, with the order number, the date, the item, "
                         "the amount and the package tracking from the email I read this morning."),
    "mail2": (NARRATOR, "Undo finds that email in its history and writes the description. Nothing gets sent."),
    # close
    "end": (NARRATOR, "Two taps on Shift to ask, Esc to stop at any time. Undo runs on Ho-lo, by H Company."),  # hyphen: long first vowel, not "hollow"
}


def key() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("ELEVENLABS_API_KEY="):
            return line.split("=", 1)[1].strip().strip("'\"")
    sys.exit("ELEVENLABS_API_KEY missing in .env")


def tts(voice: str, text: str, path: pathlib.Path, api_key: str) -> None:
    body = json.dumps({"text": text, **VOICES[voice]}).encode()
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128",
        data=body, headers={"xi-api-key": api_key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        path.write_bytes(r.read())


def level(path: pathlib.Path, target_mean: float = -20.0) -> None:
    """Bring a line to a common mean level: the two voices and models come out about 9 dB apart."""
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    mean = next(float(l.split("mean_volume:")[1].split("dB")[0]) for l in err.splitlines() if "mean_volume" in l)
    tmp = path.with_suffix(".tmp.mp3")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-af", f"volume={target_mean - mean:.2f}dB,alimiter=limit=0.95:level=false",
                    "-c:a", "libmp3lame", "-b:a", "192k", str(tmp)], check=True)
    tmp.replace(path)


def duration(path: pathlib.Path) -> float:
    out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)])
    return round(float(out), 3)


def main() -> None:
    api_key = key()
    only = set(sys.argv[1:])
    OUT.mkdir(parents=True, exist_ok=True)
    for lid, (voice, text) in LINES.items():
        p = OUT / f"{lid}.mp3"
        if (only and lid in only) or (not only and not p.exists()):
            print("tts", lid, flush=True)
            tts(voice, text, p, api_key)
            level(p)
    durs = {lid: duration(OUT / f"{lid}.mp3") for lid in LINES}
    (ROOT / "film/src/vo.json").write_text(json.dumps(durs, indent=2) + "\n")
    print(json.dumps(durs, indent=2))


if __name__ == "__main__":
    main()
