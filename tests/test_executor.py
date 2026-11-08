from PIL import Image

from undo.executor.agent import AgentExecutor
from undo.executor.control import DryRunController, parse_combo
from undo.executor.screen import ScreenSource, Screenshot
from undo.models import Action, Analysis
from undo.providers.mock import ScriptedVisionModel

ANALYSIS = Analysis(
    summary="Formulaire vidé",
    before_state="Nom=Dupont",
    recovered_content="Dupont",
    strategy="manual_redo",
    plan=["Cliquer sur Nom", "Taper Dupont", "Terminer"],
    confidence=0.9,
)


class FakeCap:
    def __init__(self, size=(2880, 1800)):
        self.size = size

    def grab(self):
        return Image.new("RGB", self.size, "white")

    def screen_size(self):
        return (1440, 900)


class UI:
    def __init__(self, confirm=True, answer="ok"):
        self.steps, self.states, self.confirms = [], [], []
        self._confirm, self._answer = confirm, answer

    def set_state(self, s, t=""):
        self.states.append(s)

    def add_step(self, t):
        self.steps.append(t)

    def confirm(self, q):
        self.confirms.append(q)
        return self._confirm

    def ask(self, q):
        return self._answer


def make_exec(settings, script, ui=None, controller=None):
    settings.dry_run = True
    settings.step_delay = 0
    settings.max_steps = 8
    ctrl = controller or DryRunController()
    screen = ScreenSource(1440, capturer=FakeCap(), logical_size=(1440, 900))
    return AgentExecutor(settings, ScriptedVisionModel(script), controller=ctrl, screen=screen, ui=ui or UI()), ctrl


def test_retina_coordinate_mapping():
    shot = Screenshot(image=Image.new("RGB", (1440, 900)), screen_w=1440, screen_h=900)
    assert shot.to_screen(500, 500) == (720, 450)
    assert shot.to_screen(1000, 1000) == (1439, 899)
    assert shot.to_screen(0, 0) == (0, 0)


def test_screen_source_downscales_retina_capture():
    shot = ScreenSource(1440, capturer=FakeCap(), logical_size=(1440, 900)).grab()
    assert shot.image.size == (1440, 900)


def test_dry_run_loop_retypes_form(settings):
    started, finished = [], []
    ex, ctrl = make_exec(
        settings,
        [("click", {"x": 250, "y": 300, "target": "Nom input"}), ("type", {"text": "Dupont", "target": "Nom"}), ("key", {"keys": "tab"}), ("done", {"text": "Formulaire restauré"})],
    )
    ex.on_start, ex.on_finish = lambda: started.append(1), lambda: finished.append(1)
    res = ex.run(ANALYSIS, "remets le formulaire")
    assert res.success and res.steps == 4
    assert ctrl.log == ["left_click(360, 270)", "type('Dupont')", "key(tab)"]
    assert started == [1] and finished == [1]
    # the model got the plan and the screenshot
    first = ex.vision.requests[0]
    assert "Dupont" in first["messages"][0]["content"]
    assert any(p["type"] == "image_url" for p in first["messages"][1]["content"])
    assert first["tools"] and first["json_schema"] is None


def test_destructive_action_requires_confirmation(settings):
    settings.confirm_sensitive = True
    ui = UI(confirm=False)
    ex, ctrl = make_exec(settings, [("click", {"x": 1, "y": 1, "target": "Supprimer le dossier", "destructive": True}), ("done", {"text": "ok"})], ui=ui)
    res = ex.run(ANALYSIS, "r")
    assert res.success
    assert ctrl.log == []  # declined -> never executed
    assert ui.confirms and "DECLINED" in res.actions[0]


def test_keyword_destructive_detection():
    assert Action(type="click", x=1, y=1, target="Send email button").needs_confirmation
    assert Action(type="key", keys="enter", reason="valider le formulaire").needs_confirmation
    assert not Action(type="click", x=1, y=1, target="Nom field").needs_confirmation


def test_password_field_is_refused(settings):
    ex, ctrl = make_exec(settings, [("type", {"text": "hunter2", "target": "Mot de passe", "is_password_field": True}), ("type", {"text": "x", "target": "password"}), ("done", {"text": "ok"})])
    res = ex.run(ANALYSIS, "r")
    assert ctrl.log == []
    assert sum("REFUSED" in a for a in res.actions) == 2


def test_ask_user_feeds_history(settings):
    ex, ctrl = make_exec(settings, [("ask_user", {"text": "Quel onglet ?"}), ("done", {"text": "ok"})], ui=UI(answer="le deuxième"))
    res = ex.run(ANALYSIS, "r")
    assert "le deuxième" in res.actions[0]
    assert "le deuxième" in ex.vision.requests[1]["messages"][1]["content"][0]["text"]


def test_invalid_tool_call_and_no_tool_call_are_tolerated(settings):
    ex, ctrl = make_exec(settings, [("click", {"x": 5000, "y": 1}), "just text", ("done", {"text": "ok"})])
    res = ex.run(ANALYSIS, "r")
    assert res.success and res.steps == 3
    assert "invalid tool call" in res.actions[0] and "no action" in res.actions[1]


def test_stop_and_max_steps(settings):
    ex, ctrl = make_exec(settings, [("wait", {"seconds": 0})] * 8)
    res = ex.run(ANALYSIS, "r")
    assert not res.success and "Maximum" in res.message
    # ESC pressed while running -> stops before the next step
    class StopOnWait(DryRunController):
        def wait(self, seconds):
            super().wait(seconds)
            ex2.stop()

    ex2, _ = make_exec(settings, [("wait", {"seconds": 0})] * 8, controller=StopOnWait())
    res2 = ex2.run(ANALYSIS, "r")
    assert res2.message.startswith("Stopped") and res2.steps == 1


def test_parse_combo_platform_mapping(monkeypatch):
    import undo.executor.control as c

    monkeypatch.setattr(c.platform, "system", lambda: "Darwin")
    assert parse_combo("cmd+shift+t") == ["command", "shift", "t"]
    monkeypatch.setattr(c.platform, "system", lambda: "Linux")
    assert parse_combo("cmd+z") == ["ctrl", "z"]


def test_holo_agent_task_text():
    from undo.executor.holo_agent import build_task

    t = build_task(ANALYSIS, "remets le formulaire")
    assert "Dupont" in t and "manual_redo" in t and "Never type passwords" in t


def test_batched_actions_fill_several_fields_in_one_call(settings):
    ex, ctrl = make_exec(settings, [
        [("type", {"x": 300, "y": 300, "text": "Dupont", "target": "Nom"}), ("type", {"x": 600, "y": 300, "text": "Marie", "target": "Prénom"}), ("done", {"text": "premature"})],
        ("done", {"text": "ok"}),
    ])
    res = ex.run(ANALYSIS, "r")
    assert res.success and res.steps == 2 and res.message == "ok"
    assert [a for a in res.actions if a.startswith("1.")] == ["1.1. type “Dupont” Nom → ok", "1.2. type “Marie” Prénom → ok"]
    assert [e.split("(")[0] for e in ctrl.log] == ["left_click", "type", "left_click", "type"]


def test_sensitive_confirmation_off_by_default(settings):
    ui = UI(confirm=False)
    ex, ctrl = make_exec(settings, [("click", {"x": 1, "y": 1, "target": "Supprimer le dossier", "destructive": True}), ("done", {"text": "ok"})], ui=ui)
    res = ex.run(ANALYSIS, "r")
    assert res.success and ctrl.log == []  # not asked for: stops right before deleting
    ex, ctrl = make_exec(settings, [("click", {"x": 1, "y": 1, "target": "Supprimer le dossier", "destructive": True}), ("done", {"text": "ok"})], ui=UI(confirm=False))
    res = ex.run(ANALYSIS, "supprime le dossier")
    assert res.success and len(ctrl.log) == 1


def test_unanswered_ask_user_stops(settings):
    ex, ctrl = make_exec(settings, [("ask_user", {"text": "Je ne vois pas le mail ?"}), ("click", {"x": 10, "y": 10}), ("done", {"text": "ok"})], ui=UI(answer=""))
    res = ex.run(ANALYSIS, "r")
    assert not res.success and res.steps == 1
    assert ctrl.log == []


def test_controls_are_listed_and_acted_on_by_id(settings, monkeypatch):
    from undo import ax

    ctl = [ax.Control(1, "AXRadioButton", "Une commande effectuée", "0"), ax.Control(2, "AXTextArea", "Description", "", 100, 200, 400, 80)]
    script = [
        [("press", {"id": 1}), ("set_text", {"id": 2, "text": "Colis jamais livré"})],
        [("done", {"text": "ok"})],
    ]
    ex, ctrl = make_exec(settings, script)
    monkeypatch.setattr(ex, "_controls", lambda app: ctl)
    pressed = []
    monkeypatch.setattr(ax, "press", lambda c: pressed.append(c.id) or True)
    monkeypatch.setattr(ax, "focus", lambda c: c.center)
    res = ex.run(ANALYSIS, "remets mon signalement")
    assert res.success
    assert pressed == [1]
    assert "left_click(300, 240)" in ctrl.log and "type('Colis jamais livré')" in ctrl.log
    assert "press #1 Une commande effectuée" in ex.ui.steps[0]
    assert ctl[1].line() == "#2 field «Description» (empty)"


def test_form_state_keeps_only_user_set_values():
    from undo import ax

    ctl = [ax.Control(1, "AXRadioButton", "A", "1"), ax.Control(2, "AXRadioButton", "B", "0"),
           ax.Control(3, "AXTextField", "Nom", "Dupont"), ax.Control(4, "AXTextField", "Vide", ""), ax.Control(5, "AXButton", "Suivant")]
    assert ax.form_state(ctl) == "[x] «A»\n«Nom» = «Dupont»"


def test_irreversible_actions_stop_unless_asked():
    from undo.executor.agent import irreversible

    assert irreversible("press #32 Enregistrer le compte rendu", "Remets le compte rendu que j'avais rempli")
    assert irreversible("click (900,700) Envoyer button", "réécris mon mail")
    assert not irreversible("click (400,300) Face-à-face radio", "remets le formulaire")
    assert not irreversible("press #14 Suivant", "Dans la description, explique que ma commande n'est jamais arrivée")
    assert not irreversible("press #32 Enregistrer le compte rendu", "remets le compte rendu et enregistre-le")


def test_replay_recorded_form_state(settings):
    from undo.ax import Control
    from undo.executor.agent import parse_form_state

    state = "«Heure» = «10:30»\n«Compte rendu» = «Visite « Nuage » au cabinet»\n[x] «Face-à-face»\n[x] «Tensiora»\n«Long» = «coupé…»"
    fields, ticked = parse_form_state(state)
    assert fields["Compte rendu"] == "Visite « Nuage » au cabinet" and ticked == {"Face-à-face", "Tensiora"}
    ex, _ = make_exec(settings, [])
    ex.replay_form = state
    controls = [Control(1, "AXTextField", "Heure"), Control(2, "AXTextArea", "Compte rendu"), Control(3, "AXRadioButton", "Face-à-face", "0"),
                Control(4, "AXCheckBox", "Tensiora", "1"), Control(5, "AXCheckBox", "Glycalm", "0"), Control(6, "AXTextField", "Long"),
                Control(7, "AXTextField", "Durée", "45 min")]
    done = []
    ex._controls = lambda app: controls
    ex._act_on_control = lambda a: done.append((a.type, a.id, a.text))
    assert ex._replay("CRM") == 3
    assert done == [("set_text", 1, "10:30"), ("set_text", 2, "Visite « Nuage » au cabinet"), ("press", 3, None)]
