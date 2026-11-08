from undo.analyzer.prompts import analyzer_user_text
from undo.executor.holo_agent import build_task
from undo.executor.prompts import executor_system
from undo.models import Analysis
from undo.recovery import playbooks_for, recovery_hints


def _analysis(app: str) -> Analysis:
    return Analysis(
        summary="Cube supprimé",
        before_state="Scène avec un cube",
        strategy="version_history",
        plan=["File > Recover > Auto Save"],
        confidence=0.8,
        target_app=app,
    )


def test_blender_playbook_matches_app_name():
    names = [p.name for p in playbooks_for([("Blender", "")])]
    assert names == ["Blender"]
    assert "File > Recover > Auto Save" in recovery_hints([("Blender", "")])


def test_web_app_matches_window_title_inside_browser():
    names = {p.name for p in playbooks_for([("Brave Browser", "Rapport - Google Docs")])}
    assert names == {"Web browser", "Google Docs / Sheets / Slides"}


def test_generic_names_do_not_match():
    assert recovery_hints([("Claude", "Claude Code"), ("Terminal", "notes.txt")]) == ""
    assert [p.name for p in playbooks_for([("Code", "")])] == ["Code editors (VS Code, Cursor)"]


def test_hints_reach_every_prompt():
    assert "Built-in recovery for Blender" in analyzer_user_text("remets mon cube", recovery_hints([("Blender", "")]))
    assert "Built-in recovery for Blender" in executor_system(_analysis("Blender"), max_steps=10)
    assert "Built-in recovery for Blender" in build_task(_analysis("Blender"), "remets mon cube")


def test_unknown_app_leaves_prompts_unchanged():
    assert "Built-in recovery" not in executor_system(_analysis("Some App"), max_steps=10)
    assert "Built-in recovery" not in build_task(_analysis(""), "x")
    assert analyzer_user_text("x").startswith("USER REQUEST")
