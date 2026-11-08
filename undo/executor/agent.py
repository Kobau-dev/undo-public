"""The agent loop: screenshot -> model (plan + history + image) -> action -> execute -> repeat."""
from __future__ import annotations

import platform
import re
import subprocess
import threading
import time
from typing import Callable

from pydantic import ValidationError

from undo.config import Settings
from undo.executor.control import Controller, DryRunController
from undo.executor.prompts import EXECUTOR_TOOLS, executor_system
from undo.executor.screen import ScreenSource, Screenshot
from undo.images import image_part, text_part
from undo.interfaces import Executor, StatusSink, VisionModel
from undo.log import get_logger
from undo.models import Action, Analysis, ExecutionResult
from undo.i18n import t

LOOP_LIMIT = 4
_IRREVERSIBLE = re.compile(
    r"\b(enregistrer|sauvegarder|envoyer|soumettre|valider|confirmer|payer|commander|publier|supprimer|effacer|"
    r"r[ée]server|save|submit|send|pay|publish|delete|confirm|checkout|place order|book)\b", re.I)
_ASKED = re.compile(r"\b(enregistr|sauvegard|envoi|envoy|soumet|soumett|valide|confirm|pai[ea]|pay|publi|supprim|efface|r[ée]serv|"
                    r"save|submit|send|publish|delete|book)", re.I)


_FIELD_LINE = re.compile(r"^«(.+?)» = «(.*)»$")
_TICK_LINE = re.compile(r"^\[x\] «(.+?)»$")


def parse_form_state(text: str) -> tuple[dict[str, str], set[str]]:
    """FORM STATE text (ax.form_state) -> ({field label: value}, {ticked labels})."""
    fields: dict[str, str] = {}
    ticked: set[str] = set()
    for line in (text or "").splitlines():
        line = line.strip()
        if m := _FIELD_LINE.match(line):
            fields[m.group(1)] = m.group(2)
        elif m := _TICK_LINE.match(line):
            ticked.add(m.group(1))
    return fields, ticked


def irreversible(target: str, request: str) -> bool:
    """A click/press on Save, Send, Pay, Delete... that the user did not ask for: Undo stops right before it."""
    return bool(_IRREVERSIBLE.search(target or "")) and not _ASKED.search(request or "")
log = get_logger("executor")


class ConsoleSink:
    def set_state(self, state, text=""):
        log.info("[%s] %s", state, text)

    def add_step(self, text):
        log.info("  → %s", text)

    def confirm(self, question):
        return input(f"{question} [y/N] ").strip().lower() in {"y", "yes", "o", "oui"}

    def ask(self, question):
        return input(f"{question} ")


class AgentExecutor(Executor):
    name = "native"

    def __init__(
        self,
        settings: Settings,
        vision: VisionModel,
        controller: Controller | None = None,
        screen: ScreenSource | None = None,
        ui: StatusSink | None = None,
        on_start: Callable[[], None] | None = None,
        on_finish: Callable[[], None] | None = None,
    ):
        self.settings = settings
        self.vision = vision
        self.controller = controller or (DryRunController() if settings.dry_run else None)
        if self.controller is None:
            from undo.executor.control import PyAutoGUIController

            self.controller = PyAutoGUIController()
        self.screen = screen or ScreenSource(settings.screenshot_max_width)
        self.ui = ui or ConsoleSink()
        self.on_start = on_start
        self.on_finish = on_finish
        self._stop = threading.Event()
        self.history: list[str] = []
        from undo.redact import build_redactor

        self.redactor = build_redactor(settings)

    cancel_event: threading.Event | None = None  # the app's Esc flag, checked as well (no race with run() clearing _stop)

    def stop(self) -> None:
        self._stop.set()

    def _stopped(self) -> bool:
        return self._stop.is_set() or (self.cancel_event is not None and self.cancel_event.is_set())

    def _on_esc(self) -> None:
        """Esc caught by the input lock (it swallows the key, so the global listener never sees it)."""
        self.stop()
        self.ui.set_state("stopped", t("Emergency stop (Esc)."))

    # -- main loop ---------------------------------------------------------
    replay_form = ""  # FORM STATE recorded before the loss, set by the app

    def run(self, analysis: Analysis, request: str) -> ExecutionResult:
        self._stop.clear()
        self.history = []
        self._batches = []
        if self.on_start:
            self.on_start()
        system = executor_system(analysis, self.settings.max_steps, getattr(self.settings, "recipe_file", None))
        self.ui.set_state("executing", t("Strategy: {strategy}", strategy=analysis.strategy))
        from undo.executor.guard import ExecutionGuard

        guard = ExecutionGuard(on_esc=self._on_esc, lock=self.settings.lock_input, glow=self.settings.glow, enabled=not self.settings.dry_run, on_blocked=getattr(self.ui, "warn", None))
        guard.start()
        try:
            if self.replay_form and analysis.strategy == "manual_redo" and not self.settings.dry_run:
                self._refocus(analysis.target_app, force=True)
                self._replay(analysis.target_app)
            for step in range(1, self.settings.max_steps + 1):
                if self._stopped():
                    return self._finish(False, step - 1, t("Stopped by the user (Esc)"))
                self._refocus(analysis.target_app, force=step == 1)
                shot = self.screen.grab()
                controls = self._controls(analysis.target_app)
                self._ctl = {c.id: c for c in controls}
                log.info("step %d: %d accessibility controls", step, len(controls))
                self._request = request
                actions = self._decide(system, request, shot, step, controls)
                if len(actions) > 1 and any(a.type == "done" for a in actions):
                    actions = [a for a in actions if a.type != "done"]  # verify on the next screenshot first
                if actions and not all(a.type == "wait" for a in actions) and self._looping(" ; ".join(a.describe() for a in actions)):
                    return self._finish(False, step, t("Loop detected: “{action}” repeated {n} times", action=actions[0].describe(), n=LOOP_LIMIT))
                for k, action in enumerate(actions):
                    if self._stopped():
                        return self._finish(False, step, t("Stopped by the user (Esc)"))
                    label = f"{step}" if len(actions) == 1 else f"{step}.{k + 1}"
                    desc = action.describe()
                    log.info("step %s: %s", label, desc)
                    self.ui.add_step(desc)
                    outcome = self._handle(action, shot, label)
                    if outcome == "done":
                        return self._finish(True, step, action.text or t("Done"))
                    if outcome == "abort":
                        return self._finish(False, step, t("No answer to: {question}", question=action.text))
                    if outcome == "break":
                        break
                    if k < len(actions) - 1:
                        time.sleep(0.15)
                time.sleep(self.settings.step_delay)
            return self._finish(False, self.settings.max_steps, t("Maximum number of steps reached"))
        finally:
            guard.stop()
            if self.on_finish:
                self.on_finish()

    def _handle(self, action: Action, shot: Screenshot, label: str) -> str:
        """Run one action; returns 'done', 'abort' (unanswered question), 'break' (drop the rest of the batch) or 'ok'."""
        desc = action.describe()
        if action.type == "done":
            return "done"
        if action.type == "ask_user":
            answer = self.ui.ask(action.text or "?")
            if not answer.strip():
                return "abort"
            self.history.append(f"{label}. ask_user «{action.text}» → user answered: «{answer}»")
            return "break"
        if action.is_password_field or (action.type == "type" and _looks_like_password_prompt(action)):
            self.history.append(f"{label}. REFUSED: typing into a password field is forbidden. Ask the user instead.")
            self.ui.add_step(t("refused: password field"))
            return "break"
        if self.settings.confirm_sensitive and action.needs_confirmation and not self.ui.confirm(t("Sensitive action: {action}. Continue?", action=desc)):
            self.history.append(f"{label}. {desc} → USER DECLINED this action; find another way or call done/ask_user.")
            return "break"
        if not (self.settings.confirm_sensitive and action.needs_confirmation) and action.type in {"click", "double_click", "press", "key"}:
            target = desc
            if action.type == "press":
                ctl = getattr(self, "_ctl", {}).get(action.id if action.id is not None else -1)
                target = f"{desc} {ctl.label if ctl else ''}"
            if action.type == "key" and (action.keys or "").lower() not in {"enter", "return", "command+s", "ctrl+s", "command+enter", "ctrl+enter"}:
                target = ""
            if target and irreversible(target, getattr(self, "_request", "")):
                log.info("stopping before irreversible action: %s", desc)
                self.ui.add_step(t("stopped before saving / sending"))
                return "done"
        try:
            self._execute(action, shot)
            self.history.append(f"{label}. {desc} → ok")
            return "ok"
        except Exception as exc:
            log.warning("action failed: %s", exc)
            self.history.append(f"{label}. {desc} → FAILED: {exc}")
            return "break"

    # -- helpers ---------------------------------------------------------------
    def _refocus(self, target_app: str | None, force: bool = False) -> None:
        """If another app stole the focus (a notification, a chat window...), bring the target app back before
        looking at the screen, so we never type into the wrong window."""
        if not target_app or platform.system() != "Darwin" or self.settings.dry_run:
            return
        try:
            from undo import ax
            from undo.recorder.platform import MacForeground

            pid = ax._pid(target_app)
            if pid is not None:  # by pid: works when the process name differs from the app's visible name
                front = ax._front_pids()
                if force or not front or front[0] != pid:
                    from AppKit import NSApplicationActivateIgnoringOtherApps, NSRunningApplication

                    log.info("activating %r (pid %d)", target_app, pid)
                    NSRunningApplication.runningApplicationWithProcessIdentifier_(pid).activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
                    time.sleep(0.6)
                return
            app, _ = MacForeground().foreground()
            # window order can say "target" while another app (the overlay, a launcher) holds the keyboard focus,
            # and a click on a non-key window is often swallowed: always activate once before the first action
            if not force and app and (app.lower() in target_app.lower() or target_app.lower() in app.lower()):
                return
            log.info("foreground is %r, re-activating %r", app, target_app)
            subprocess.run(["osascript", "-e", f'tell application "{target_app}" to activate'], check=False, timeout=5)
            time.sleep(0.8)
        except Exception as exc:
            log.debug("refocus failed: %s", exc)

    def _replay(self, target_app: str | None) -> int:
        """Put back the exact recorded values (accessibility FORM STATE) into the matching EMPTY fields and unticked
        boxes of the target window; the model then checks the result and does the rest."""
        from undo import ax

        fields, ticked = parse_form_state(self.replay_form)
        if not fields and not ticked:
            return 0
        controls = self._controls(target_app)
        self._ctl = {c.id: c for c in controls}
        n = 0
        for c in controls:
            if self._stopped():
                break
            try:
                if c.role in ax.FIELD_ROLES and c.label in fields:
                    v = fields[c.label]
                    if not v or v.endswith("…") or (c.value or "").strip():
                        continue
                    self._act_on_control(Action(type="set_text", id=c.id, text=v))
                elif c.role in ax.TOGGLE_ROLES and c.label in ticked and not c.checked:
                    self._act_on_control(Action(type="press", id=c.id))
                else:
                    continue
                n += 1
                self.history.append(f"0. «{c.label}» put back from the recorded form state → ok")
                time.sleep(0.1)
            except Exception as exc:
                log.warning("replay of %r failed: %s", c.label, exc)
        if n:
            log.info("replayed %d recorded values", n)
            self.ui.add_step(t("{n} values restored from history", n=n))
        return n

    def _repeat_warning(self) -> str:
        """The same action twice in a row usually means it had no effect: say so before the model tries a third time."""
        b = getattr(self, "_batches", [])
        if len(b) >= 2 and b[-1] == b[-2] and not b[-1].startswith("wait"):
            return (f"\n\nWARNING: you already did «{b[-1]}» twice and the screen did not change as expected. "
                    "Do NOT do it again: aim at a different element (re-read the step and find its label), or press Esc and start the step over.")
        return ""

    def _looping(self, desc: str) -> bool:
        """Same action chosen LOOP_LIMIT times in a row (e.g. the screen never changes) -> give up."""
        self._batches = getattr(self, "_batches", [])[-(LOOP_LIMIT - 1):] + [desc]
        return len(self._batches) == LOOP_LIMIT and len(set(self._batches)) == 1

    def _controls(self, target_app: str | None) -> list:
        if self.settings.dry_run or not self.settings.ax or not target_app:
            return []
        from undo import ax

        return ax.snapshot(target_app, budget=1.0) if ax.available() else []

    def _decide(self, system: str, request: str, shot: Screenshot, step: int, controls: list | None = None) -> list[Action]:
        hist = "\n".join(self.history[-15:]) or "(no actions yet)"
        listing = ""
        if controls:
            lines = [c.line() for c in controls[:180]]
            listing = "\n\nCONTROLS of the target window (use their #id with set_text / press):\n" + "\n".join(lines)
        user = [
            text_part(f"User request: «{request}»\nStep {step}/{self.settings.max_steps}. Previous actions:\n{hist}{listing}{self._repeat_warning()}\n\nCurrent screenshot below. Choose the next action."),
            image_part(self.redactor(shot.image) if self.redactor else shot.image, quality=70),
        ]
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        resp = self.vision.complete(messages, tools=EXECUTOR_TOOLS, temperature=0.3, thinking=True, max_tokens=1024)
        if not resp.tool_calls:
            log.warning("model returned no tool call (content=%r)", (resp.content or "")[:200])
            self.history.append(f"{step}. (no action chosen — you must call at least one tool)")
            return []
        actions = []
        for call in resp.tool_calls[:12]:
            try:
                act = Action.model_validate({"type": call.name, **call.arguments})
                ctl = getattr(self, "_ctl", {}).get(act.id) if act.id is not None else None
                if ctl is not None and not act.target:
                    act.target = ctl.label
                actions.append(act)
            except ValidationError as exc:
                msg = str(exc).splitlines()[0]
                log.warning("invalid action %s(%s): %s", call.name, call.arguments, msg)
                self.history.append(f"{step}. invalid tool call {call.name}: {msg}")
                break
        return actions

    def _execute(self, a: Action, shot: Screenshot) -> None:
        c = self.controller
        if a.type == "move":
            c.move(*shot.to_screen(a.x or 0, a.y or 0))
        elif a.type in {"click", "double_click", "right_click"}:
            x, y = shot.to_screen(a.x or 0, a.y or 0)
            c.click(x, y, button="right" if a.type == "right_click" else "left", clicks=2 if a.type == "double_click" else 1)
        elif a.type == "type":
            if a.x is not None and a.y is not None:
                c.click(*shot.to_screen(a.x, a.y))
                time.sleep(0.1)
            c.type_text(a.text or "")
        elif a.type in {"set_text", "press"}:
            self._act_on_control(a)
        elif a.type == "key":
            c.key(a.keys or "")
        elif a.type == "scroll":
            x, y = shot.to_screen(a.x or 500, a.y or 500)
            c.scroll(x, y, a.dx, a.dy)
        elif a.type == "open_app":
            c.open_app(a.text or "")
        elif a.type == "wait":
            c.wait(a.seconds)

    def _act_on_control(self, a: Action) -> None:
        from undo import ax

        ctl = getattr(self, "_ctl", {}).get(a.id if a.id is not None else -1)
        if ctl is None:
            raise ValueError(f"no control #{a.id} in the current CONTROLS list")
        c = self.controller
        if a.type == "press":
            if not ax.press(ctl):
                center = ax.focus(ctl)
                if not center:
                    raise RuntimeError(f"cannot press #{a.id}")
                c.click(int(center[0]), int(center[1]))
            return
        center = ax.focus(ctl)
        if center:  # a real click: web pages only take typing into the field they consider focused
            c.click(int(center[0]), int(center[1]))
            time.sleep(0.1)
        c.key("cmd+a")
        c.type_text(a.text or "")

    def _finish(self, ok: bool, steps: int, message: str) -> ExecutionResult:
        self.ui.set_state("done" if ok else "failed", message)
        log.info("executor finished: ok=%s steps=%d %s", ok, steps, message)
        return ExecutionResult(success=ok, steps=steps, message=message, actions=list(self.history))


def _looks_like_password_prompt(a: Action) -> bool:
    hay = f"{a.target} {a.reason}".lower()
    return any(w in hay for w in ("password", "mot de passe", "passcode", "passwd"))
