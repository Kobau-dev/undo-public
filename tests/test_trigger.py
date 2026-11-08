import numpy as np

from undo.config import Settings
from undo.providers.mock import FakeTranscriber
from undo.trigger.mic import SilenceDetector, pcm_to_wav
from undo.trigger.trigger import Trigger


class StubUI:
    def __init__(self, answer="texte"):
        self.states = []
        self.answer = answer

    def set_state(self, state, text=""):
        self.states.append(state)

    def add_step(self, text):
        pass

    def confirm(self, q):
        return True

    def ask(self, q):
        return self.answer


class StubMic:
    def __init__(self, wav: bytes, available=True):
        self.wav = wav
        self._available = available

    def available(self):
        return self._available

    def record(self):
        return self.wav

    def request_stop(self):
        pass


def test_silence_detector_stops_after_speech_then_silence():
    sr = 16000
    det = SilenceDetector(silence_seconds=1.0, max_seconds=30, sample_rate=sr)
    quiet = np.zeros(sr // 4, dtype=np.float32)
    loud = (np.random.default_rng(0).standard_normal(sr // 4) * 0.2).astype(np.float32)
    assert det.feed(quiet) is False  # leading silence never stops
    assert det.feed(loud) is False
    assert det.feed(quiet) is False
    assert det.feed(quiet) is False
    assert det.feed(quiet) is False
    assert det.feed(quiet) is True  # 1.0 s of quiet after speech


def test_silence_detector_max_duration():
    det = SilenceDetector(silence_seconds=2.0, max_seconds=0.5, sample_rate=16000)
    assert det.feed(np.zeros(8000, dtype=np.float32)) is True


def test_pcm_to_wav_header():
    wav = pcm_to_wav(np.zeros(1600, dtype=np.int16))
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"


def test_trigger_voice_path(settings):
    got = []
    ui = StubUI()
    t = Trigger(settings, FakeTranscriber("remets le formulaire"), ui, got.append, mic=StubMic(b"RIFF...."))
    t.fire()
    assert got == ["remets le formulaire"]
    assert "listening" in ui.states and "transcribing" in ui.states


def test_trigger_falls_back_to_text_without_mic(settings):
    got = []
    ui = StubUI(answer="retrouve ma note")
    t = Trigger(settings, FakeTranscriber("x"), ui, got.append, mic=StubMic(b"", available=False))
    t.fire()
    assert got == ["retrouve ma note"]


def test_trigger_falls_back_to_text_without_transcriber(settings):
    got = []
    t = Trigger(settings, None, StubUI(answer="hello"), got.append, mic=StubMic(b"RIFF", available=True))
    t.fire()
    assert got == ["hello"]


def test_trigger_typed_request_wins_over_voice(settings):
    got = []

    class TypingUI(StubUI):
        def prompt_input(self, question, on_submit):
            self.on_submit = on_submit
            return lambda: setattr(self, "closed", True)

    class TypedWhileRecording(StubMic):
        def record(self):
            ui.on_submit("remets ma note")
            return self.wav

    ui = TypingUI()
    t = Trigger(settings, FakeTranscriber("ignored"), ui, got.append, mic=TypedWhileRecording(b"RIFF"))
    t.fire()
    assert got == ["remets ma note"] and ui.closed and "transcribing" not in ui.states


def test_trigger_pauses_around_prompt(settings):
    events = []
    t = Trigger(settings, FakeTranscriber("remets le formulaire"), StubUI(), lambda r: events.append("request"), mic=StubMic(b"RIFF...."),
                on_open=lambda: events.append("open"), on_close=lambda: events.append("close"))
    t.fire()
    assert events == ["open", "request", "close"]


def test_trigger_voice_disabled_asks_text(settings):
    settings.voice = False
    got = []
    t = Trigger(settings, FakeTranscriber("bruit ambiant"), StubUI(answer="remets la description"), got.append, mic=StubMic(b"RIFF", available=True))
    t.fire()
    assert got == ["remets la description"]


def test_trigger_multiline_request_becomes_one_line(settings):
    got = []
    ui = StubUI()
    t = Trigger(settings, FakeTranscriber("Remets le formulaire\nque j'avais rempli\r\n  avant l'expiration.\n"), ui, got.append, mic=StubMic(b"RIFF...."))
    t.fire()
    assert got == ["Remets le formulaire que j'avais rempli avant l'expiration."]


def test_trigger_blank_lines_only_is_nothing_heard(settings):
    got = []
    ui = StubUI()
    Trigger(settings, FakeTranscriber("\n \n"), ui, got.append, mic=StubMic(b"RIFF....")).fire()
    assert got == [] and ui.states[-1] == "idle"


def test_trigger_esc_while_listening_drops_request(settings):
    got = []
    ui = StubUI()

    class EscMic(StubMic):
        def record(self):
            assert t.cancel()
            return self.wav

    t = Trigger(settings, FakeTranscriber("remets le formulaire"), ui, got.append, mic=EscMic(b"RIFF...."))
    t.fire()
    assert got == [] and ui.states[-1] == "stopped" and "transcribing" not in ui.states
    assert not t.cancel()  # nothing being captured any more


def test_trigger_esc_while_typing_drops_request(settings):
    settings.voice = False
    got = []

    class EscUI(StubUI):
        def ask(self, q):
            t.cancel()
            return ""  # what cancel_input() makes the bubble answer

    ui = EscUI()
    t = Trigger(settings, None, ui, got.append, mic=StubMic(b""))
    t.fire()
    assert got == [] and ui.states[-1] == "stopped"


class BoxUI(StubUI):
    """A text box like the macOS bubble: the transcript lands in it and only Enter sends it."""

    def __init__(self, on_fill=None):
        super().__init__()
        self.filled = []
        self.closed = False
        self.on_fill = on_fill

    def prompt_input(self, question, on_submit):
        self.on_submit = on_submit
        return lambda: setattr(self, "closed", True)

    def fill_input(self, text):
        self.filled.append(text)
        if self.on_fill:
            self.on_fill()
        return True


def test_trigger_transcript_waits_for_enter(settings):
    got = []

    def enter():
        assert got == []  # in the box, not sent
        ui.on_submit("remets le formulaire de Marie")  # what the user corrected it to

    ui = BoxUI(on_fill=enter)
    Trigger(settings, FakeTranscriber("remets le formulaire de mari"), ui, got.append, mic=StubMic(b"RIFF....")).fire()
    assert ui.filled == ["remets le formulaire de mari"]
    assert got == ["remets le formulaire de Marie"] and ui.closed and "heard" in ui.states


def test_trigger_esc_with_transcript_in_the_box_drops_it(settings):
    got = []
    ui = BoxUI(on_fill=lambda: t.cancel())
    t = Trigger(settings, FakeTranscriber("remets le formulaire"), ui, got.append, mic=StubMic(b"RIFF...."))
    t.fire()
    assert got == [] and ui.states[-1] == "stopped" and ui.closed


def test_trigger_transcript_never_sent_is_dropped(settings):
    got = []
    ui = BoxUI()
    t = Trigger(settings, FakeTranscriber("remets le formulaire"), ui, got.append, mic=StubMic(b"RIFF...."))
    t.review_timeout = 0.05
    t.fire()
    assert got == [] and ui.states[-1] == "stopped"


def test_trigger_typing_turns_the_mic_off_and_keeps_the_text(settings):
    got = []
    stops = []

    class TypingStartsMic(StubMic):
        def record(self):
            ui.on_input_edited()
            return self.wav

        def request_stop(self):
            stops.append(True)

    class NoTranscript:
        def transcribe(self, wav, languages):
            raise AssertionError("what the user types replaces the transcription")

    ui = BoxUI(on_fill=lambda: ui.on_submit("remets ma note"))
    Trigger(settings, NoTranscript(), ui, got.append, mic=TypingStartsMic(b"RIFF....")).fire()
    assert stops and ui.filled == [None] and got == ["remets ma note"]
