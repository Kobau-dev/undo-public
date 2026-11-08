"""Gladia pre-recorded speech-to-text (https://docs.gladia.io/chapters/pre-recorded-stt/quickstart).

Flow: POST /v2/upload (multipart) -> audio_url ; POST /v2/pre-recorded -> result_url ; poll until status == done.
"""
from __future__ import annotations

import json
import queue
import threading
import time
from typing import Callable

import requests

from undo.interfaces import Transcriber
from undo.log import get_logger

log = get_logger("gladia")


class GladiaTranscriber(Transcriber):
    name = "gladia"

    def __init__(self, api_key: str, base_url: str = "https://api.gladia.io", poll_interval: float = 1.0, timeout: float = 90.0):
        self.base_url = base_url.rstrip("/")
        self.headers = {"x-gladia-key": api_key}
        self.poll_interval = poll_interval
        self.timeout = timeout

    def transcribe(self, wav_bytes: bytes, languages: list[str] | None = None) -> str:
        languages = [l.strip() for l in (languages or ["fr", "en"]) if l.strip()]
        t0 = time.time()
        up = requests.post(
            f"{self.base_url}/v2/upload",
            headers=self.headers,
            files={"audio": ("undo.wav", wav_bytes, "audio/wav")},
            timeout=60,
        )
        up.raise_for_status()
        audio_url = up.json()["audio_url"]

        body = {
            "audio_url": audio_url,
            "language_config": {"languages": languages, "code_switching": len(languages) > 1},
            "punctuation_enhanced": True,
        }
        job = requests.post(f"{self.base_url}/v2/pre-recorded", headers=self.headers, json=body, timeout=30)
        job.raise_for_status()
        result_url = job.json()["result_url"]

        deadline = time.time() + self.timeout
        while time.time() < deadline:
            res = requests.get(result_url, headers=self.headers, timeout=30)
            res.raise_for_status()
            data = res.json()
            status = data.get("status")
            if status == "done":
                text = data["result"]["transcription"]["full_transcript"].strip()
                log.info("transcribed in %.1fs: %s", time.time() - t0, text)
                return text
            if status == "error":
                raise RuntimeError(f"Gladia error: {data.get('error_code')} {data.get('error')}")
            time.sleep(self.poll_interval)
        raise TimeoutError("Gladia transcription timed out")

    def live_session(self, languages: list[str] | None, on_text: Callable[[str], None]) -> "GladiaLive":
        langs = [l.strip() for l in (languages or ["fr"]) if l.strip()]
        return GladiaLive(self.headers, langs, on_text, base_url=self.base_url)


class GladiaLive:
    """Streaming session (https://docs.gladia.io/chapters/live-stt/quickstart): partial transcripts while the user speaks.
    send() is safe to call from the audio callback (frames are queued and sent by a worker thread)."""

    def __init__(self, headers: dict, languages: list[str], on_text: Callable[[str], None], base_url: str = "https://api.gladia.io", sample_rate: int = 16000):
        self.headers = headers
        self.languages = languages
        self.on_text = on_text
        self.base_url = base_url.rstrip("/")
        self.sample_rate = sample_rate
        self._utterances: dict[str, str] = {}
        self._full = ""
        self._done = threading.Event()
        self._out: queue.Queue[bytes | None] = queue.Queue()
        self._ws = None

    def start(self) -> None:
        import websocket

        body = {
            "encoding": "wav/pcm",
            "sample_rate": self.sample_rate,
            "bit_depth": 16,
            "channels": 1,
            "language_config": {"languages": self.languages, "code_switching": False},
            "messages_config": {"receive_partial_transcripts": True, "receive_final_transcripts": True},
        }
        res = requests.post(f"{self.base_url}/v2/live", headers=self.headers, json=body, timeout=10)
        res.raise_for_status()
        self._ws = websocket.create_connection(res.json()["url"], timeout=10)
        self._ws.settimeout(60)
        threading.Thread(target=self._reader, daemon=True, name="gladia-live-rx").start()
        threading.Thread(target=self._sender, daemon=True, name="gladia-live-tx").start()

    def send(self, pcm16: bytes) -> None:
        self._out.put(pcm16)

    def text(self) -> str:
        return " ".join(t for t in self._utterances.values() if t).strip()

    def finish(self, timeout: float = 6.0) -> str:
        """Stop recording and wait for the final transcript."""
        self._out.put(None)
        self._done.wait(timeout)
        self.close()
        return self._full or self.text()

    def close(self) -> None:
        self._out.put(None)
        try:
            if self._ws:
                self._ws.close()
        except Exception:
            pass

    def _sender(self) -> None:
        while True:
            chunk = self._out.get()
            try:
                if chunk is None:
                    self._ws.send(json.dumps({"type": "stop_recording"}))
                    return
                self._ws.send_binary(chunk)
            except Exception as exc:
                log.debug("gladia live send failed: %s", exc)
                return

    def _reader(self) -> None:
        try:
            while True:
                raw = self._ws.recv()
                if not raw:
                    break
                msg = json.loads(raw)
                kind = msg.get("type")
                if kind == "transcript":
                    data = msg.get("data") or {}
                    self._utterances[str(data.get("id"))] = ((data.get("utterance") or {}).get("text") or "").strip()
                    self.on_text(self.text())
                elif kind == "post_final_transcript":
                    tr = ((msg.get("data") or {}).get("transcription") or {})
                    self._full = (tr.get("full_transcript") or "").strip()
                    self._done.set()
                elif kind == "end_session":
                    break
        except Exception as exc:
            log.debug("gladia live closed: %s", exc)
        finally:
            self._done.set()
