# Undo

> Undo keeps a history of what happened on your Mac, and can act on it.

Hackathon **H Company × 42AI — Computer Use Agents** (Paris, 2026).

**The idea.** ⌘Z goes back one step at a time, inside one app. Undo starts from a record of what passed on your screen, so it
can act on the past, even when there is nothing to undo.

**How it works**
1. **History** — regular screenshots, read locally by Apple Vision OCR and indexed (SQLite FTS5) on your Mac.
2. **Request** — two taps on Shift, then speak: **Gladia** transcribes your words (EN/FR) into the bubble's text field, and only Enter sends them.
3. **Reading** — **Holo** (H Company) reads the history and picks the right moments.
4. **Action** — Holo drives the real mouse and keyboard in the open app, with no plugin.

**Three examples: undo, recover, reuse**

| Example | The situation | What Undo does | What it shows |
|---|---|---|---|
| **Blender** | In software you don't master, you delete the pool and the deck, then keep working. ⌘Z would erase everything since. | Goes back, copies the objects, returns to the present and pastes them in place. | Undoing without losing anything, without being an expert. |
| **CRM** | A visit report is filled in, the session expires, the form comes back empty. | Finds the last state of the form and fills every field, then stops before saving. | Recovering what the app did not keep. |
| **Mail, then SignalConso** | No mistake at all. A delivery email was read earlier, and now you have to file a complaint. | Finds the email in the history and writes the description. Nothing is sent. | Reusing something seen earlier, from one app to another. |

**You stay in control**
- Your request only goes when you press Enter.
- A light around the screen and a named pointer show when the agent is acting.
- Esc stops it at any time.
- It is built to stop before Save, Send, Submit, Pay or Delete unless you asked for it.

---

## Try it in 5 minutes (jury)

You need a Mac (macOS, Python 3.11+: `make` picks a compatible version on its own) and two keys:
[H Company](https://hub.hcompany.ai/) and, for voice, [Gladia](https://app.gladia.io/) (without it, you type your request).

```bash
git clone https://github.com/Kobau-dev/undo-public && cd undo-public
make install && make test                       # simulated models: no key or macOS needed (the CRM tests also need .[crm])
make install-macos && cp .env.example .env      # then put H_API_KEY and GLADIA_API_KEY in .env
make run                                        # leave it running, grant the permissions below
```

Grant the [macOS permissions](#macos-permissions-system-settings--privacy--security) to your terminal, then quit it
completely (⌘Q), reopen it and run `make run` again: the Undo bubble should appear.

Main scenario (real software, nothing is sent). Undo must already be running: it only finds what it has seen.

1. In a second terminal, from the `undo-public` folder: `open demo/parcel.eml`. The Maison du Lit order email opens in Mail
   (order MDL-20261018-4472, tracking CE-77-4410-928). Leave it visible for a few seconds.
2. On https://signal.conso.gouv.fr/en, start a report under "Online purchases" → order never delivered → website
   `www.maisondulit-exemple.fr`, up to the Description field.
3. ⇧ ⇧ (two quick taps on Shift), then say or type: *"In the description, explain that my order never arrived, with the
   order number, date, item, amount and parcel tracking from this morning's email."* Your words land in the bubble's
   text field: press Enter to send them.

Undo finds the email in its history, writes the description and stops before sending. Esc cancels the request or stops Undo at any time.
The other scenarios (expiring form, setting that breaks something, deleted note, CRM…): [`demo/README.md`](demo/README.md).

## Installation (macOS Apple Silicon, Python 3.11+)

```bash
git clone https://github.com/Kobau-dev/undo-public && cd undo-public
make install-macos          # venv + deps + ocrmac/pyobjc/rumps
cp .env.example .env        # then fill in H_API_KEY and GLADIA_API_KEY
```

`make` takes the first Python ≥ 3.11 on the PATH; to force one: `make install-macos PY=python3.12`.
Or by hand: `python3 -m venv .venv && .venv/bin/pip install -e ".[dev,macos]"` (with a `python3` ≥ 3.11).

### macOS permissions (System Settings → Privacy & Security)

Grant these to the **terminal / app that runs Python** (Terminal, iTerm, VS Code…):

| Permission | Why | If it is missing |
|---|---|---|
| **Screen Recording** | the Recorder captures the screen (`screencapture`) | Undo cannot see your windows and finds nothing |
| **Accessibility** | the Executor moves the mouse and types (`pyautogui`), reads and fills fields | no actions, ⇧ ⇧ may do nothing |
| **Input Monitoring** | the global ⇧ ⇧ shortcut and the Esc key (`pynput`) | ⇧ ⇧ does nothing |
| **Microphone** | the Trigger records your spoken request | you have to type your request |
| **Automation** (asked at the first action) | bringing the target app to the front before acting | the agent may act in the wrong window |

The first run triggers some of these prompts; add the terminal by hand to any list where it does not appear. macOS only
applies these rights when the app restarts: quit the terminal (⌘Q), reopen it, then run `make run` again. At startup, `make run`
names any missing Screen Recording, Accessibility or Input Monitoring permission in the terminal.

## Running

The `python -m undo …` and `pip …` commands in this README and in `demo/README.md` assume the venv is active:
`source .venv/bin/activate`.

```bash
make run                 # = python -m undo run      (recorder + shortcut + overlay)
make dry-run             # the agent prints its actions instead of executing them
make demo                # serves the demo mini-apps on http://localhost:8765
python -m undo menubar   # menu bar icon: on/off, pause, buffer length
```

Usage: work normally. When you need something from your history: **⇧ ⇧ (two quick taps on Shift)**, then say or type your request. What
you say lands in the bubble's text field, where you can correct it. Only **Enter** sends the request, whether you spoke or
typed; **Esc** cancels it. The overlay then shows *analysis → "I understood: …" → steps → done*. While the agent acts, a light
runs around the screen edge and its pointer carries an "Undo" label. **Esc** also stops the agent immediately.

Other commands:

```bash
python -m undo run --request "restore the form"        # no voice or shortcut (tests)
python -m undo run --executor holo-agent               # hands the restore to H's Agents API (local desktop)
python -m undo record                                  # recorder only
python -m undo export recordings/demo1 --minutes 10    # saves the recording so you can replay it
python -m undo analyze --replay recordings/demo1 "I lost the form"   # Analyzer only, without redoing the demo
python -m undo analyze --replay recordings/demo1 "…" --execute --dry-run       # + simulated execution
python -m undo status                                  # recorder stats
python -m undo models                                  # Holo models available with your key
```

Detailed demo scenarios (what the human does, the sentence to say, the expected result): [`demo/README.md`](demo/README.md).

## Configuration

Variables (`.env`): `H_API_KEY` (or `HAI_API_KEY`), `GLADIA_API_KEY`, and optionally `UNDO_LANG` (on-screen text: English by
default, `fr` for French), `UNDO_MODEL` (`holo4-35b-a3b` by default — the fastest; `holo4-27b` the most capable;
`holo3-1-35b-a3b` free), `UNDO_BUFFER_MINUTES` (480 = 8 h), `UNDO_CAPTURE_INTERVAL` (1.5 s), `UNDO_LOOKBACK_MINUTES` (15),
`UNDO_EXCLUDED_APPS` (1Password, Keychain Access… never recorded), `UNDO_HOTKEY` (`double:shift` by default (⌥ ⌥ is taken by
Siri on some Macs); also `double:alt`, `double:cmd`, `double:alt_r` or a combo like `<cmd>+<shift>+z`), `UNDO_MAX_STEPS` (40),
`UNDO_DATA_DIR` (`~/.undo`), `UNDO_VOICE=0` (typed requests only, no microphone), `UNDO_LIVE_STT=0` (no live transcription in
the bubble), `UNDO_AX=0` (without macOS accessibility), `UNDO_REDACT=1` (blurs sensitive data), `UNDO_CONFIRM=1`
(confirmation before sensitive actions).

## Architecture

```
undo/
  recorder/   capture (screencapture on macOS, mss elsewhere) → phash dedup → JPEG ring buffer → SQLite FTS5 ← OCR (thread); frontmost app; exclusions; pause
  trigger/    global shortcut (pynput) → microphone (sounddevice) → Gladia → text in the bubble, sent with Enter; typed fallback
  analyzer/   selects 5 keyframes (OCR match, content drop = the mistake, current state) → Holo → strict JSON (pydantic, retry)
  executor/   loop screenshot → Holo (function calling, coordinates [0,1000]) → action → pyautogui; Retina; Esc; confirmations; --dry-run
              holo_agent.py: alternative through H's Agents API ({"kind": "desktop"})
  ax.py       macOS accessibility: reads the fields (label, value, ticked boxes) of any app, web pages included,
              records them with each capture and fills them directly on restore (vision stays as the fallback)
  ui/         native macOS bubble (Liquid Glass, AppKit, separate process); tkinter overlay elsewhere; console; rumps menu bar
  providers/  holo.py (Models API, OpenAI-compatible), gladia.py, mock.py — behind VisionModel / Transcriber / Executor
demo/         web mini-apps, native desktop CRM (crm_app/, PySide6), demo emails, Blender scene, takes/ (how the film's takes are shot)
tests/        recorder, index, trigger, analyzer, executor, safeguards, CRM, end to end in dry-run
film/         Remotion edit of the demo video, from the raw takes (voices, subtitles)
```

### Analyzer JSON

```json
{
  "summary": "what was lost / broken",
  "before_state": "precise description of the state to restore",
  "recovered_content": "exact text to retype if applicable",
  "strategy": "native_undo | version_history | trash | manual_redo",
  "plan": ["step 1", "step 2"],
  "confidence": 0.0,
  "target_app": "Safari"
}
```

### H Company technical choices (checked against the docs at hub.hcompany.ai)

- Models API `https://api.hcompany.ai/v1`, `openai` client. Max **5 images / request** → 5 keyframes.
- Native grounding: integer coordinates **[0, 1000] normalized to the image sent**; we scale them to screen points
  (Retina handling: capture in device pixels, logical size from `pyautogui.size()`).
- Analyzer: `structured_outputs={"json": schema}` (enforced at decoding); Executor: function calling with
  `tool_choice="required"` (the two do not mix in one request).
- Agents API: `pip install "hai-agents[desktop]"` + environment `{"kind": "desktop"}` does drive a local desktop
  (macOS/Windows/Linux) → `--executor holo-agent` mode. The native mode stays the default to keep the overlay,
  the confirmations and the recorder pause under control.

## What gets recorded (local, `~/.undo`, rolling 8 h buffer, `UNDO_BUFFER_MINUTES`)

- JPEG screenshots (~1.5 s, only when the screen changes) + OCR + app/title/position of the active window.
- Keyboard/mouse log (`UNDO_INPUT_LOG=1` by default): typed text grouped by window, shortcuts (⌘Z, ⌘W…),
  clicks. Never in a password field (macOS secure input, or a field detected through accessibility for apps that
  do not enable it), in excluded apps, or while Undo is acting.
  On macOS, allow "Input Monitoring" for the terminal / app that runs Undo.
- Sent to the model only when you make a request: 5 keyframes (cropped to the window) + their OCR and form values + the
  text typed in the relevant time window; then one screenshot per action during the restore.
- Optional blurring (`UNDO_REDACT=1`): card numbers (Luhn), IBANs and API keys are blurred in images before they go to H (one extra OCR pass per image).
- Models: Analyzer and Executor `holo4-35b-a3b` (benchmark on a real recording: 6.5 s analysis and valid JSON first time 4/4, against 14–40 s with retries for `holo4-27b`; same quality; `holo3-122b` does not handle tool calls).

## Validated for real (H + Gladia keys)

- `python -m undo models`: lists `holo3-1-35b-a3b`, `holo3-122b-a10b`, `holo4-27b`, `holo4-35b-a3b`.
- Analyzer on a replayed recording of the "lost form" demo: valid JSON first time in ~5 s,
  `manual_redo`, all 8 fields found in `recovered_content`.
- Holo grounding: Name field, Email field, error banner → exact coordinates (~0.5 s / call).
- Gladia: transcription of a test wav in ~5 s.
- End to end on a Linux VM (no OCR): real recorder + `form.html` demo in Chrome + real executor →
  the 8 fields (including a dropdown and 2 textareas with accents) restored in 17 steps / ~1 min 40.
  Without OCR, the Analyzer spots the mistake from the drop in JPEG size (a full form compresses ~20% less well).
- macOS (MacBook Air M-series, macOS 26, 1470×956 Retina ×2 screen): capture + Apple Vision OCR (~0.7 s / screen),
  frontmost app detection, Accessibility, Holo from the Mac, then the real "lost form" scenario:
  recorder → 8 fields filled → expiry → `undo analyze --execute` restores the fields in Brave (analysis ~6 s,
  ~1.5 s per action). macOS traps found and fixed: `mss` takes 30 s per capture on macOS 26 (we use
  `screencapture`, 0.15 s); `NSWorkspace.frontmostApplication()` is frozen in a daemon with no run loop (CGWindowList);
  a window that takes focus during the restore (notification, chat) makes it type in the wrong place → the executor
  re-activates the target app before each capture.
- Demos filmed for real on macOS (the takes in the film, request sent → done): Maison du Lit email (Mail app) → SignalConso
  description (real site, nothing submitted) in ~16 s; visit report in a desktop CRM (Qt, demo app) restored after a session
  expiry, all 11 values, in ~27 s, without clicking "Save"; pool and deck put back in a Blender scene in ~30 s (scripted scene,
  prepared steps with `UNDO_RECIPE`). In those takes the spoken requests are ElevenLabs voices fed straight into Undo's audio
  input (`demo/takes/run_undo.py`), so they follow the normal Gladia → bubble → Enter flow with the Mac's sound off; the
  flow with the real microphone (live Gladia transcription) is validated end to end too.

## Security and privacy

- Stored on your machine only: captures, OCR, index. When you make a request, up to 5 keyframes with their OCR and form values, plus the text typed in that
  time window, go to Holo, then one screenshot per action during the restore; the audio of the request goes to Gladia.
- Excluded apps are never captured (password managers); pause from the menu bar.
- Esc = immediate stop. Undo stops before actions it recognises as Save, Send, Submit, Pay, Delete… unless the request
  asks for them (a check in the code, not just in the model's instructions); `UNDO_CONFIRM=1` adds a confirmation. The
  check matches words in the action the model describes, so it is a safety net, not a guarantee: keep an eye on the screen.
- The agent refuses to type into fields it identifies as password fields.
- Undo works from what was seen or typed during the history window. The model can misread it, so check the result.
- The Recorder pauses while the agent acts (so it does not record itself).

## Known limits

- Built and tested on macOS. Linux was only tried on a VM, without OCR.
- The keyboard log is on by default and the text typed in the relevant time window goes to Holo with a request; turn it off with `UNDO_INPUT_LOG=0`.
- Your keyboard and mouse are blocked while the agent acts (Esc still works); turn this off with `UNDO_LOCK_INPUT=0`.
- A request looks back 15 minutes by default (`UNDO_LOOKBACK_MINUTES`).

## Development

```bash
make test            # pytest (no key or macOS needed: mocked providers)
UNDO_DEBUG=1 python -m undo run -v
```

Logs: each step is logged (rich) and each run saved to `~/.undo/runs/<ts>.json`
(request, keyframes, analysis, actions, result).

## Stack

- **H Company (Holo)**: the agent that reads the history and controls the computer
- **Gladia**: transcription of the spoken request
- **Apple Vision OCR**: reading the screen locally
- **Python**: the orchestration
- **Devin**: developed the code in this repo (recorder, trigger, analyzer, executor, overlay, demos, tests) from the specification and the H / Gladia docs
- **Claude Code**: English version, Enter-to-send flow, agent cursor, takes and film
