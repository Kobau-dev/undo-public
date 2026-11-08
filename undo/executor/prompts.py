EXECUTOR_SYSTEM = """You are Undo, an agent that controls a computer (mouse + keyboard) to restore something the user lost.
At each step you receive the CURRENT screenshot and the history of your previous actions. Decide the next action(s) by
calling tools. Coordinates x,y are integers in [0, 1000], normalized to the screenshot (origin top-left).
Be fast: when several actions only depend on what is ALREADY visible on this screenshot (e.g. filling several visible
form fields), call several tools in the same response, in order; they run back to back and you see the result on the
next screenshot. Stop the batch at anything that changes the layout (scroll, open a menu/dropdown, navigation).

Context from the analysis:
- What happened: {summary}
- State to restore: {before_state}
- Strategy: {strategy}
- Plan: {plan}
- Exact content to retype (if any):
<<<
{recovered_content}
>>>
{recovery}
Rules:
- Follow the plan but adapt to what you actually see. Verify the previous action worked before moving on.
- To fill a field, call `type` with its x,y (it clicks the field first) and the exact text from the recovered content
  (multi-line is fine). One `type` per field, all visible fields in one batch.
- When a CONTROLS list is given (the window's real fields/buttons, read from the app), PREFER `set_text` for fields and
  `press` for radio buttons, checkboxes, buttons, links and menus, by control id: exact, and it works even when the
  control is off-screen (no scrolling needed). Batch several, but end the batch after a press that reveals new options
  or changes the page (e.g. "Suivant"/"Next"/"Continuer"): the next step brings a fresh CONTROLS list. Use the x,y
  tools only for what is not in the list.
- Do not `wait` unless the screenshot shows something still loading (spinner, blank page): act right away.
- Never move a multi-step form forward (Suivant / Next / Continuer / Valider) unless a restored value lives on a later
  step; once the last value is in place, stay on that step and call `done`.
- Call `done` alone, only after a screenshot shows the state restored.
- Prefer the app's built-in recovery (menus above, if any) over re-creating things by hand; with strategy manual_redo,
  retype the recovered content directly.
- Prefer keyboard shortcuts when reliable (Cmd+Z, Cmd+Shift+T to reopen a tab, Cmd+S...).
- Set destructive=true on any click/key that deletes, sends, pays, submits or confirms something: the user will be asked.
- Restore the state, then stop: never Send / Submit / Pay / Save (no Cmd+S, no save dialog) unless the user's request
  explicitly asks for it. Call done and let the user check, save or send.
- NEVER type a password. If a field is a password field, set is_password_field=true and use ask_user instead.
- Do not touch anything unrelated to the restoration.
- When the state is restored, call `done` with a one-sentence result. If stuck or something is ambiguous, call `ask_user`.
- You have at most {max_steps} steps."""


RECIPE_HEADER = """
PREPARED INSTRUCTIONS (written in advance for exactly this situation; they override the plan above).
Do them in order, one or two actions per turn. After each action look at the new screenshot and check the
expected result written in the step before moving on. If a step had no visible effect, do NOT repeat the same
click: re-read the step, look for the named label on the screenshot and aim at it, or press Esc and redo the step.
"""


def _recipe_block(recipe_file: str | None) -> str:
    if not recipe_file:
        return ""
    try:
        with open(recipe_file, encoding="utf-8") as f:
            return RECIPE_HEADER + f.read().strip() + "\n"
    except OSError:
        return ""


def executor_system(analysis, max_steps: int, recipe_file: str | None = None) -> str:
    return EXECUTOR_SYSTEM.format(
        summary=analysis.summary,
        before_state=analysis.before_state,
        strategy=analysis.strategy,
        plan="\n  ".join(f"{i}. {s}" for i, s in enumerate(analysis.plan, 1)),
        recovered_content=analysis.recovered_content or "(none)",
        recovery=_recovery_block(analysis),
        max_steps=max_steps,
    ) + _recipe_block(recipe_file)


def _recovery_block(analysis) -> str:
    from undo.recovery import recovery_hints

    if analysis.strategy == "manual_redo":  # the analysis ruled built-in recovery out (unsaved doc, cleared form)
        return ""
    hints = recovery_hints([(analysis.target_app, analysis.summary)])  # summary names the web app (Google Docs...)
    return f"\n{hints}\n" if hints else ""


def _xy(desc: str) -> dict:
    return {
        "type": "object",
        "properties": {
            "x": {"type": "integer", "minimum": 0, "maximum": 1000, "description": "X in [0,1000] on the screenshot"},
            "y": {"type": "integer", "minimum": 0, "maximum": 1000, "description": "Y in [0,1000] on the screenshot"},
            "target": {"type": "string", "description": desc},
            "destructive": {"type": "boolean", "description": "True if this deletes/sends/pays/submits/confirms"},
            "reason": {"type": "string"},
        },
        "required": ["x", "y", "target"],
    }


def _fn(name: str, description: str, params: dict) -> dict:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": params}}


EXECUTOR_TOOLS = [
    _fn("click", "Left click at a point.", _xy("What is clicked, e.g. 'Nom input field'")),
    _fn("double_click", "Double click at a point.", _xy("What is double-clicked")),
    _fn("move", "Move the mouse pointer to a point WITHOUT clicking (hover a menu, or put the pointer over an area "
        "before a keyboard shortcut that acts on the area under the pointer).", _xy("Where the pointer goes")),
    _fn("right_click", "Right click at a point.", _xy("What is right-clicked")),
    _fn(
        "type",
        "Type text into a field (clicked first when x,y are given) or the focused field. Use \\n for new lines.",
        {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "x": {"type": "integer", "minimum": 0, "maximum": 1000, "description": "Field X: clicked first to focus it (omit to type into the focused field)"},
                "y": {"type": "integer", "minimum": 0, "maximum": 1000, "description": "Field Y"},
                "target": {"type": "string", "description": "The field being filled"},
                "is_password_field": {"type": "boolean"},
                "reason": {"type": "string"},
            },
            "required": ["text"],
        },
    ),
    _fn(
        "key",
        "Press a key or shortcut, e.g. 'enter', 'cmd+z', 'cmd+shift+t', 'tab'.",
        {"type": "object", "properties": {"keys": {"type": "string"}, "destructive": {"type": "boolean"}, "reason": {"type": "string"}}, "required": ["keys"]},
    ),
    _fn(
        "scroll",
        "Scroll at a point. dy>0 scrolls up, dy<0 scrolls down (units of ~1 line, use 5-10).",
        {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}, "dx": {"type": "integer"}, "dy": {"type": "integer"}, "reason": {"type": "string"}}, "required": ["x", "y", "dy"]},
    ),
    _fn(
        "set_text",
        "Replace the content of the field #id from the CONTROLS list with text (it is focused and scrolled into view).",
        {"type": "object", "properties": {"id": {"type": "integer"}, "text": {"type": "string"}, "target": {"type": "string", "description": "The field label"}, "is_password_field": {"type": "boolean"}, "reason": {"type": "string"}}, "required": ["id", "text"]},
    ),
    _fn(
        "press",
        "Press the control #id from the CONTROLS list (tick a radio/checkbox, click a button/link, open a menu).",
        {"type": "object", "properties": {"id": {"type": "integer"}, "target": {"type": "string", "description": "The control label"}, "destructive": {"type": "boolean"}, "reason": {"type": "string"}}, "required": ["id"]},
    ),
    _fn("open_app", "Open or focus an application by name.", {"type": "object", "properties": {"text": {"type": "string", "description": "Application name"}}, "required": ["text"]}),
    _fn("wait", "Wait for the UI to settle.", {"type": "object", "properties": {"seconds": {"type": "number"}}, "required": ["seconds"]}),
    _fn("done", "The state is restored.", {"type": "object", "properties": {"text": {"type": "string", "description": "What was restored"}}, "required": ["text"]}),
    _fn("ask_user", "Ask the user a question and wait for the answer.", {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}),
]
