# Blender demo: the villa and the pool deleted too early

An architect models a contemporary villa in Blender (glazed ground floor, cantilevered upper floor, cladding, pool, wood
deck). They want to hide the pool and the deck, **delete** them by mistake, then keep working (carport, trees, dark
cladding, sun, camera). A plain ⌘Z would erase all of that work.

Undo steps back in time (⌘Z ×6), copies the pool and the deck in the past (⌘C), returns to the present (⇧⌘Z ×8) and pastes
them back in their exact place (⌘V). The carport, the trees and the rest are kept. About 20 s of execution, 5 turns.

## What's here

| File | Role |
|---|---|
| `villa_demo.py` | Replays the modelling session in Blender, one named entry per step in Edit > Undo History, with the mistake in the middle |
| `recipe_villa.md` | Prepared instructions for the agent (loaded with `UNDO_RECIPE`): without them, Holo hesitates in Blender's menus |
| `ask.py` | ⇧ ⇧, then types the request in the Undo bubble |
| `take.sh` | A full take with a typed request: restarts Blender, records the screen, logs the mouse, asks Undo, waits for the end |
| `cursor_log.py`, `hover.py` | Mouse log (60 Hz) and a move without a click |

Videos and logs go to `demo/blender/out/` (ignored by git). The empty project file `villa_martin.blend` is created on the
first run (opening a file skips Blender's splash screen).

## Requirements

- Blender 4.2 or newer in `/Applications` (tested with 5.2.3), or `BLENDER=/path/to/Blender`.
- `ffmpeg` (`brew install ffmpeg`), Undo installed in `.venv` with the H key in `.env`.
- For the terminal running the scripts: **Screen Recording** and **Accessibility** permissions.
- The Mac's display at its default resolution. Don't touch the mouse or keyboard during a take (about 2 min).

## Shooting a take

Terminal 1: Undo, with a blank memory for the take and the prepared instructions:

```bash
mkdir -p demo/blender/out
UNDO_DATA_DIR=demo/blender/out/undo_data UNDO_VOICE=0 UNDO_HUD_CAPTURABLE=1 UNDO_STEP_DELAY=0.3 UNDO_RECIPE=demo/blender/recipe_villa.md .venv/bin/python -m undo run -v 2>&1 | tee demo/blender/out/undo.log
```

Terminal 2: the take (from the repository root):

```bash
zsh demo/blender/take.sh 1
```

Result: `demo/blender/out/take1.mov` and `take1_cursor.jsonl`. The end of the log must show `step 1.x: key cmd+z` ×6,
`cmd+c`, `cmd+shift+z` ×8, `cmd+v`, then `executor finished: ok=True`.

- Blank `UNDO_DATA_DIR`: otherwise Undo can bring back values from an earlier take.
- `UNDO_HUD_CAPTURABLE=1`: the bubble, the edge light and the agent cursor appear in the recording.
- `UNDO_STEP_DELAY=0.3`: a livelier agent between two actions (0.8 s by default).

`demo/takes/shoot.py blender` shoots the same scene in full screen, with the spoken request played to the microphone.

Check the manoeuvre without Undo (Blender does it alone and writes the result to the log):

```bash
VILLA_SELFTEST=1 VILLA_SPEED=0.3 VILLA_LOG=/tmp/villa.log /Applications/Blender.app/Contents/MacOS/Blender --factory-startup demo/blender/villa_martin.blend --python demo/blender/villa_demo.py
```

`after paste: 35 ['Pool', 'Water', 'Wood deck'] carport=True` means the recovery works.

## Known traps (and why the scene is built this way)

- **Undo History list**: dense, Holo aims badly at it (one line off). The recipe uses ⌘Z / ⇧⌘Z on the keyboard, which is reliable.
- **⌘C / ⌘V** only act when the mouse is over the 3D view: the agent uses the `move` action (no click). In the past, a click
  in the scene would create a new step and erase everything after it.
- **Selection**: the pool is already selected at the "Material: Larch" step and at "Select"; going back one step too many or
  too few still copies the right thing.
- **Esc**: the agent sometimes closes a menu with Esc; that is no longer mistaken for the user's emergency stop.
- **AZERTY keyboard**: the request is typed as Unicode events, independent of the layout.
- No lock screen during a take (keep the Mac awake).
