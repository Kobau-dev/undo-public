"""Synthesize the sound effects and the music bed locally (numpy only, nothing downloaded).

Usage: python3 film/tools/sfx.py   -> film/public/sfx/*.wav
"""
import pathlib
import wave

import numpy as np

SR = 44100
OUT = pathlib.Path(__file__).resolve().parents[1] / "public/sfx"
rng = np.random.default_rng(7)


def save(name: str, x: np.ndarray, gain: float = 0.9) -> None:
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        x = np.stack([x, x], axis=1)
    peak = np.max(np.abs(x)) or 1.0
    x = x / peak * gain
    with wave.open(str(OUT / f"{name}.wav"), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype("<i2").tobytes())


def t(sec: float) -> np.ndarray:
    return np.arange(int(sec * SR)) / SR


def env(n: int, attack: float, decay: float) -> np.ndarray:
    tt = np.arange(n) / SR
    a = np.clip(tt / max(attack, 1e-4), 0, 1)
    return a * np.exp(-tt / decay)


def lowpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    f = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / SR)
    f *= 1 / (1 + (freqs / cutoff) ** 4)
    return np.fft.irfft(f, len(x))


def highpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    return x - lowpass(x, cutoff)


def click() -> np.ndarray:
    """Trackpad / mouse click: short filtered noise burst + tiny body."""
    n = int(0.06 * SR)
    noise = highpass(rng.standard_normal(n), 1800) * env(n, 0.0005, 0.004)
    body = np.sin(2 * np.pi * 1900 * t(0.06)) * env(n, 0.0005, 0.006) * 0.4
    return noise + body


def key(seed: int) -> np.ndarray:
    r = np.random.default_rng(seed)
    n = int(0.07 * SR)
    noise = lowpass(highpass(r.standard_normal(n), 900), 5200) * env(n, 0.0008, 0.010)
    thock = np.sin(2 * np.pi * r.uniform(180, 260) * t(0.07)) * env(n, 0.001, 0.012) * 0.6
    return (noise + thock) * r.uniform(0.7, 1.0)


def typing(seconds: float, cps: float, seed: int) -> np.ndarray:
    """A typing bed: irregular key presses, a few louder ones (space bar)."""
    r = np.random.default_rng(seed)
    out = np.zeros(int(seconds * SR) + SR)
    pos = 0.05
    i = 0
    while pos < seconds:
        k = key(seed * 1000 + i)
        if r.random() < 0.15:
            k = k * 1.3
        s = int(pos * SR)
        out[s:s + len(k)] += k
        pos += r.gamma(4, 1 / (4 * cps))
        i += 1
    return out[: int(seconds * SR)]


def double_shift() -> np.ndarray:
    a = key(11) * 1.2
    gap = np.zeros(int(0.13 * SR))
    return np.concatenate([a, gap, key(12) * 1.2, np.zeros(int(0.1 * SR))])


def shortcut() -> np.ndarray:
    """Modifier + key: two soft presses very close together."""
    return np.concatenate([key(21) * 0.8, np.zeros(int(0.03 * SR)), key(22), np.zeros(int(0.05 * SR))])


def rewind(seconds: float = 1.2) -> np.ndarray:
    """Tape-rewind flutter: rising chirps of filtered noise, fading out."""
    tt = t(seconds)
    n = len(tt)
    noise = rng.standard_normal(n)
    band = lowpass(highpass(noise, 1200), 6000)
    flutter = 0.55 + 0.45 * np.sin(2 * np.pi * (14 + 18 * tt / seconds) * tt)
    chirp = np.sin(2 * np.pi * (400 * tt + 900 * tt ** 2)) * 0.25
    shape = np.clip(tt / 0.08, 0, 1) * np.clip((seconds - tt) / 0.35, 0, 1)
    return (band * flutter * 0.5 + chirp) * shape


def ding() -> np.ndarray:
    """Soft confirmation: two sine notes (E6 then B6) with gentle decay."""
    def note(f: float, d: float) -> np.ndarray:
        tt = t(d)
        e = env(len(tt), 0.004, 0.35)
        return (np.sin(2 * np.pi * f * tt) + 0.25 * np.sin(2 * np.pi * 2 * f * tt)) * e
    a = note(1318.5, 1.0)
    b = note(1975.5, 1.2)
    out = np.zeros(int(1.4 * SR))
    out[: len(a)] += a * 0.8
    s = int(0.09 * SR)
    out[s:s + len(b)] += b * 0.6
    return out


def whoosh(seconds: float = 0.7) -> np.ndarray:
    tt = t(seconds)
    n = len(tt)
    noise = rng.standard_normal(n)
    # sweep a band-pass by mixing a low and high filtered version over time
    lo = lowpass(noise, 700)
    hi = lowpass(highpass(noise, 1500), 7000)
    mix = tt / seconds
    shape = np.sin(np.pi * np.clip(tt / seconds, 0, 1)) ** 2
    out = (lo * (1 - mix) + hi * mix * 0.6) * shape
    return np.stack([out * (1 - 0.5 * mix), out * (0.5 + 0.5 * mix)], axis=1)


def music(seconds: float = 170.0, bpm: float = 92.0) -> np.ndarray:
    """Calm bed: soft pad chords (Am - F - C - G) + a muted pulse. Low in the mix."""
    tt = t(seconds)
    beat = 60 / bpm
    bar = beat * 4
    chords = [(220.0, 261.63, 329.63), (174.61, 220.0, 261.63), (196.0, 261.63, 329.63), (196.0, 246.94, 293.66)]
    pad = np.zeros_like(tt)
    for i in range(int(seconds / bar) + 1):
        start = i * bar
        notes = chords[i % 4]
        m = (tt >= start) & (tt < start + bar + 0.6)
        local = tt[m] - start
        e = np.clip(local / 0.5, 0, 1) * np.clip((bar + 0.6 - local) / 0.6, 0, 1)
        for f in notes:
            for det in (-0.6, 0.6):
                pad[m] += np.sin(2 * np.pi * (f + det) * tt[m]) * e * 0.08
        # bass
        pad[m] += np.sin(2 * np.pi * notes[0] / 2 * tt[m]) * e * 0.10
    pad = lowpass(pad, 1400)
    pulse = np.zeros_like(tt)
    k = int(0.18 * SR)
    for i in range(int(seconds / (beat / 2))):
        s = int(i * beat / 2 * SR)
        if s + k > len(pulse):
            break
        f = chords[int(i * beat / 2 / bar) % 4][2] * 2
        pulse[s:s + k] += np.sin(2 * np.pi * f * t(0.18)) * env(k, 0.003, 0.05) * (0.05 if i % 2 else 0.08)
    out = pad + pulse
    fade = np.clip(tt / 2.0, 0, 1) * np.clip((seconds - tt) / 3.0, 0, 1)
    out = out * fade
    left = out
    right = np.roll(out, int(0.012 * SR))
    return np.stack([left, right], axis=1)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    save("click", click(), 0.8)
    save("double_shift", double_shift(), 0.8)
    save("shortcut", shortcut(), 0.7)
    save("typing_user", typing(12, 9, 1), 0.55)
    save("typing_agent", typing(12, 16, 2), 0.5)
    save("rewind", rewind(1.2), 0.6)
    save("ding", ding(), 0.55)
    save("whoosh", whoosh(0.7), 0.5)
    save("music", music(), 0.5)
    print(sorted(p.name for p in OUT.glob("*.wav")))


if __name__ == "__main__":
    main()
