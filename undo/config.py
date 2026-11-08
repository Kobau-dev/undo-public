"""Runtime settings, loaded from environment / .env."""
from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DEFAULT_EXCLUDED_APPS = [
    "1Password",
    "Keychain Access",
    "Trousseau d'accès",
    "Passwords",
    "Mots de passe",
    "Bitwarden",
    "KeePassXC",
]


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    # providers
    h_api_key: str | None = field(default_factory=lambda: _env("H_API_KEY") or _env("HAI_API_KEY"))
    h_base_url: str = field(default_factory=lambda: _env("H_BASE_URL", "https://api.hcompany.ai/v1"))
    model: str = field(default_factory=lambda: _env("UNDO_MODEL", "holo4-35b-a3b"))  # executor: fast grounding loop
    # analyzer ("the brain"): one call that must read 5 screenshots and plan -> holo4-35b-a3b by default (fastest, same quality)
    analyzer_model: str = field(default_factory=lambda: _env("UNDO_ANALYZER_MODEL", "holo4-35b-a3b"))
    analyzer_effort: str = field(default_factory=lambda: _env("UNDO_ANALYZER_EFFORT", "medium"))  # holo4-27b: low|medium|xhigh
    gladia_api_key: str | None = field(default_factory=lambda: _env("GLADIA_API_KEY"))
    gladia_languages: list[str] = field(default_factory=lambda: (_env("UNDO_LANGUAGES", "en,fr") or "").split(","))

    # recorder
    data_dir: Path = field(default_factory=lambda: Path(_env("UNDO_DATA_DIR", "~/.undo")).expanduser())
    buffer_minutes: int = field(default_factory=lambda: int(_env("UNDO_BUFFER_MINUTES", "480")))
    capture_interval: float = field(default_factory=lambda: float(_env("UNDO_CAPTURE_INTERVAL", "1.5")))
    frame_max_width: int = field(default_factory=lambda: int(_env("UNDO_FRAME_MAX_WIDTH", "1600")))
    jpeg_quality: int = field(default_factory=lambda: int(_env("UNDO_JPEG_QUALITY", "70")))
    phash_threshold: int = field(default_factory=lambda: int(_env("UNDO_PHASH_THRESHOLD", "4")))
    excluded_apps: list[str] = field(
        default_factory=lambda: [a.strip() for a in (_env("UNDO_EXCLUDED_APPS") or ",".join(DEFAULT_EXCLUDED_APPS)).split(",") if a.strip()]
    )
    ocr_enabled: bool = field(default_factory=lambda: _bool("UNDO_OCR", True))
    redact: bool = field(default_factory=lambda: _bool("UNDO_REDACT", False))
    confirm_sensitive: bool = field(default_factory=lambda: _bool("UNDO_CONFIRM", False))  # ask before delete/send/pay-like clicks  # blur card numbers/IBANs/secrets before sending to H
    # typed text / clicks / shortcuts, local only, never during macOS secure input (password fields)
    lock_input: bool = field(default_factory=lambda: _bool("UNDO_LOCK_INPUT", True))  # swallow user input while acting (macOS)
    glow: bool = field(default_factory=lambda: _bool("UNDO_GLOW", True))  # Siri-like halo + banner while acting (macOS)
    input_log: bool = field(default_factory=lambda: _bool("UNDO_INPUT_LOG", True))
    ax: bool = field(default_factory=lambda: _bool("UNDO_AX", True))  # macOS accessibility: record form values, act by control id

    # trigger
    hotkey: str = field(default_factory=lambda: _env("UNDO_HOTKEY", "double:shift"))
    voice: bool = field(default_factory=lambda: _bool("UNDO_VOICE", True))  # 0: typed requests only (noisy room)
    live_transcription: bool = field(default_factory=lambda: _bool("UNDO_LIVE_STT", True))
    silence_seconds: float = field(default_factory=lambda: float(_env("UNDO_SILENCE_SECONDS", "2.0")))
    max_record_seconds: float = field(default_factory=lambda: float(_env("UNDO_MAX_RECORD_SECONDS", "30")))

    # analyzer / executor
    lookback_minutes: int = field(default_factory=lambda: int(_env("UNDO_LOOKBACK_MINUTES", "15")))
    timeline_selection: bool = field(default_factory=lambda: _bool("UNDO_TIMELINE", True))  # model picks keyframes from a text timeline
    max_keyframes: int = 5  # Holo models accept at most 5 images per request
    max_steps: int = field(default_factory=lambda: int(_env("UNDO_MAX_STEPS", "40")))
    step_delay: float = field(default_factory=lambda: float(_env("UNDO_STEP_DELAY", "0.8")))
    # optional file of step-by-step instructions prepared in advance for a known situation (demo, support script)
    recipe_file: str | None = field(default_factory=lambda: _env("UNDO_RECIPE"))
    screenshot_max_width: int = field(default_factory=lambda: int(_env("UNDO_SCREENSHOT_MAX_WIDTH", "1440")))
    executor_backend: str = field(default_factory=lambda: _env("UNDO_EXECUTOR", "native"))  # native | holo-agent
    dry_run: bool = False

    @property
    def frames_dir(self) -> Path:
        return self.data_dir / "frames"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "frames.db"

    @property
    def control_path(self) -> Path:
        return self.data_dir / "control.json"

    @property
    def is_macos(self) -> bool:
        return platform.system() == "Darwin"

    def ensure_dirs(self) -> None:
        self.frames_dir.mkdir(parents=True, exist_ok=True)
