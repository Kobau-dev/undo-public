"""Alternative executor: let H's Agents API drive the local desktop (pip install "hai-agents[desktop]").

Docs: https://hub.hcompany.ai/agents-api/your-desktop — an agent with a {"kind": "desktop"} environment runs
on this machine via the SDK bridge; the Python process must have Screen Recording + Accessibility permissions.
Kill switch: Esc twice. Here the restoration task is written from our Analysis and handed to the agent.
"""
from __future__ import annotations

from undo.config import Settings
from undo.interfaces import Executor, StatusSink
from undo.log import get_logger
from undo.models import Analysis, ExecutionResult
from undo.recovery import recovery_hints
from undo.i18n import t

log = get_logger("holo-agent")


def build_task(analysis: Analysis, request: str) -> str:
    plan = "\n".join(f"{i}. {s}" for i, s in enumerate(analysis.plan, 1))
    content = f"\nExact content to retype:\n<<<\n{analysis.recovered_content}\n>>>" if analysis.recovered_content else ""
    hints = "" if analysis.strategy == "manual_redo" else recovery_hints([(analysis.target_app, analysis.summary)])
    hints = f"\n\n{hints}\nPrefer these built-in recovery menus over re-creating things by hand." if hints else ""
    return (
        f"The user said: «{request}». What happened: {analysis.summary}\n"
        f"Restore this state on the current desktop: {analysis.before_state}\n"
        f"Strategy: {analysis.strategy}. Steps:\n{plan}{content}{hints}\n"
        "Only touch what is needed for the restoration. Never type passwords. Stop when the state is restored and say what you did."
    )


class HoloAgentExecutor(Executor):
    name = "holo-agent"

    def __init__(self, settings: Settings, ui: StatusSink, on_start=None, on_finish=None):
        self.settings = settings
        self.ui = ui
        self.on_start = on_start
        self.on_finish = on_finish
        self._session_id = None

    def run(self, analysis: Analysis, request: str) -> ExecutionResult:
        try:
            from hai_agents import Client  # type: ignore
        except ImportError as exc:
            raise RuntimeError('hai-agents not installed: pip install "hai-agents[desktop]"') from exc
        import os

        os.environ.setdefault("HAI_API_KEY", self.settings.h_api_key or "")
        task = build_task(analysis, request)
        if self.settings.dry_run:
            self.ui.add_step("[dry-run] holo-agent task:\n" + task)
            return ExecutionResult(success=True, steps=0, message="dry-run", actions=[task])
        if self.on_start:
            self.on_start()
        try:
            client = Client()
            agent = client.agents.create_agent(
                name="undo-desktop",
                description="Undo: restores a lost state on the user's own desktop.",
                environments=[{"id": "undo-laptop", "kind": "desktop", "screenshot_max_width": 1440}],
                model=self.settings.model,
            )
            self.ui.set_state("executing", t("H agent (holo-desktop) running…"))
            result = client.run_session(agent=agent, messages=task)
            ok = str(getattr(result, "status", "")).lower() == "completed"
            answer = str(getattr(result, "answer", "") or "")
            self.ui.set_state("done" if ok else "failed", answer[:200])
            return ExecutionResult(success=ok, steps=0, message=answer, actions=[task])
        finally:
            if self.on_finish:
                self.on_finish()
