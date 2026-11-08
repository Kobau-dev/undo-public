import json
import time

import pytest

from undo.analyzer import Analyzer, select_keyframes
from undo.analyzer.analyzer import _extract_json
from undo.providers.mock import ScriptedVisionModel
from tests.conftest import record_scene

FORM_LINES = [
    "Dossier administratif",
    "Nom: Dupont",
    "Prénom: Marie",
    "Adresse: 12 rue des Lilas, 75011 Paris",
    "Motif de la demande: renouvellement de passeport suite à perte",
]

GOOD = {
    "summary": "Le formulaire s'est vidé après l'expiration de la session.",
    "before_state": "Formulaire rempli: Nom Dupont, Prénom Marie, Adresse 12 rue des Lilas, Motif renouvellement passeport",
    "recovered_content": "Dupont\nMarie\n12 rue des Lilas, 75011 Paris\nrenouvellement de passeport suite à perte",
    "strategy": "manual_redo",
    "plan": ["Cliquer sur le champ Nom", "Taper Dupont", "Cliquer sur Prénom", "Taper Marie"],
    "confidence": 0.86,
    "target_app": "Safari",
}


def _scenes():
    return [
        (700, ["Dossier administratif", "Nom:", "Prénom:", "Adresse:"], ("Safari", "Dossier administratif")),
        (500, FORM_LINES[:3], None),
        (300, FORM_LINES, None),
        (120, ["Session expirée", "Veuillez recommencer"], None),
        (5, ["Dossier administratif", "Nom:", "Prénom:", "Adresse:"], None),
    ]


def test_select_keyframes_picks_before_error_and_current(recorder):
    frames = record_scene(recorder, _scenes())
    kfs = select_keyframes(recorder.index, "j'ai perdu le formulaire passeport adresse rue des Lilas", lookback_minutes=15, max_frames=5)
    assert 1 <= len(kfs) <= 5
    roles = {k.role: k for k in kfs}
    assert roles["current"].frame.id == frames[-1].id
    assert roles["before"].frame.id == frames[2].id  # the full form
    assert roles["error"].frame.id == frames[3].id  # session expired
    assert [k.ts for k in kfs] == sorted(k.ts for k in kfs)


def test_select_keyframes_respects_lookback(recorder):
    record_scene(recorder, _scenes())
    kfs = select_keyframes(recorder.index, "formulaire", lookback_minutes=1, max_frames=5)
    assert len(kfs) == 1 and kfs[0].role == "current"


def test_analyzer_returns_valid_json_and_sends_max_5_images(recorder, settings):
    record_scene(recorder, _scenes())
    model = ScriptedVisionModel([GOOD])
    analysis = Analyzer(settings, model, recorder.index).analyze("j'ai perdu le formulaire passeport")
    assert analysis.strategy == "manual_redo"
    assert "Dupont" in analysis.recovered_content
    req = model.requests[0]
    assert req["json_schema"]["title"] == "Analysis"
    images = [p for p in req["messages"][1]["content"] if p["type"] == "image_url"]
    assert 1 <= len(images) <= 5
    captions = " ".join(p["text"] for p in req["messages"][1]["content"] if p["type"] == "text")
    assert "rue des Lilas" in captions  # OCR is passed to the model
    assert "CURRENT SCREEN" in captions


def test_analyzer_retries_on_invalid_json(recorder, settings):
    record_scene(recorder, _scenes())
    bad_plan = dict(GOOD, plan=[])
    model = ScriptedVisionModel(["not json at all", bad_plan, "```json\n" + json.dumps(GOOD) + "\n```"])
    analysis = Analyzer(settings, model, recorder.index).analyze("formulaire")
    assert analysis.confidence == pytest.approx(0.86)
    assert len(model.requests) == 3
    # the retry carries the error hint
    assert "not valid JSON" in model.requests[1]["messages"][-1]["content"]


def test_analyzer_gives_up(recorder, settings):
    record_scene(recorder, _scenes())
    model = ScriptedVisionModel(["x", "y", "z"])
    with pytest.raises(RuntimeError):
        Analyzer(settings, model, recorder.index).analyze("formulaire")


def test_analyzer_without_frames(recorder, settings):
    with pytest.raises(RuntimeError):
        Analyzer(settings, ScriptedVisionModel([GOOD]), recorder.index).analyze("formulaire")


def test_extract_json():
    assert _extract_json('Sure: {"a": 1} ok') == '{"a": 1}'
    with pytest.raises(ValueError):
        _extract_json("nothing")


def test_select_keyframes_without_ocr_uses_jpeg_size(tmp_path):
    """No OCR available (e.g. Linux dev box): the frame with most pixels-of-content before a sharp size drop is 'before'."""
    from undo.models import Frame
    from undo.recorder.index import FrameIndex

    index = FrameIndex(tmp_path / "frames.db")
    now = time.time()
    sizes = [50_000, 80_000, 95_000, 76_000, 77_000]  # empty, filling, full, expired, now
    ids = []
    for i, size in enumerate(sizes):
        p = tmp_path / f"f{i}.jpg"
        p.write_bytes(b"\0" * size)
        ids.append(index.add(Frame(ts=now - (len(sizes) - i) * 10, app="chrome", path=str(p))))
    roles = {k.role: k for k in select_keyframes(index, "formulaire", now=now, lookback_minutes=15, max_frames=5)}
    assert roles["before"].frame.id == ids[2]
    assert roles["error"].frame.id == ids[3]
    assert roles["current"].frame.id == ids[4]


def _frame(index, tmp_path, ts, text, name):
    from undo.models import Frame

    p = tmp_path / f"{name}.jpg"
    p.write_bytes(b"\0" * 1000)
    return index.add(Frame(ts=ts, app="chrome", path=str(p), ocr_text=text))


def test_select_keyframes_finds_match_hours_old(tmp_path):
    from undo.recorder.index import FrameIndex

    index = FrameIndex(tmp_path / "frames.db")
    now = time.time()
    old = _frame(index, tmp_path, now - 5 * 3600, "Devis client Acme montant 12 400 euros conditions de paiement", "old")
    for i in range(3):
        _frame(index, tmp_path, now - 60 * (3 - i), "Boîte de réception Gmail", f"r{i}")
    without = select_keyframes(index, "devis Acme", now=now, lookback_minutes=15)
    assert old not in {k.frame.id for k in without}
    with_buffer = select_keyframes(index, "devis Acme", now=now, lookback_minutes=15, search_minutes=480)
    assert old in {k.frame.id for k in with_buffer}


def test_parse_time_hint():
    from datetime import datetime

    from undo.analyzer.search import parse_time_hint

    now = datetime(2026, 11, 7, 17, 0).timestamp()
    a, b = parse_time_hint("remets le devis d'il y a 2 h", now)
    assert a < now - 7200 < b
    a, b = parse_time_hint("le texte que j'avais vers 14h30", now)
    assert a < datetime(2026, 11, 7, 14, 30).timestamp() < b
    a, b = parse_time_hint("ce que j'ai fait ce matin", now)
    assert a == datetime(2026, 11, 7, 6, 0).timestamp()
    assert parse_time_hint("remets le formulaire", now) is None


def test_select_keyframes_includes_other_window(tmp_path):
    from undo.models import Frame
    from undo.recorder.index import FrameIndex

    index = FrameIndex(tmp_path / "frames.db")
    now = time.time()

    def add(ts, app, title, text):
        p = tmp_path / f"{ts}.jpg"
        p.write_bytes(b"\0" * 1000)
        return index.add(Frame(ts=now - ts, app=app, window_title=title, path=str(p), ocr_text=text))

    for t in (60, 50, 40):
        add(t, "Brave Browser", "Déclaration de sinistre", "Numéro de dossier Date du sinistre Montant")
    mail = add(30, "Safari", "Messagerie", "Votre sinistre Numéro de dossier SIN-2026-07731 Date 28/10/2026")
    for t in (20, 10, 5, 0):
        add(t, "Brave Browser", "Déclaration de sinistre", "Numéro de dossier Date du sinistre Montant")
    kfs = select_keyframes(index, "remplis avec le numéro de dossier du mail", now=now, lookback_minutes=15, max_frames=5)
    assert mail in {k.frame.id for k in kfs}


def test_timeline_pick_keyframes(tmp_path):
    from undo.analyzer.timeline import build_timeline, pick_keyframes
    from undo.models import Frame
    from undo.providers.mock import ScriptedVisionModel
    from undo.recorder.index import FrameIndex

    index = FrameIndex(tmp_path / "frames.db")
    now = time.time()

    def add(ts, app, title, text):
        p = tmp_path / f"{ts}.jpg"
        p.write_bytes(b"\0" * 1000)
        return index.add(Frame(ts=now - ts, app=app, window_title=title, path=str(p), ocr_text=text))

    add(90, "Brave Browser", "Déclaration", "Numéro de dossier")
    mail = add(60, "Safari", "Messagerie", "Votre sinistre SIN-2026-07731")
    add(55, "Safari", "Messagerie", "Votre sinistre")
    add(30, "Brave Browser", "Déclaration", "Numéro de dossier")
    cur = add(0, "Brave Browser", "Déclaration", "Numéro de dossier")
    text, ids, current = build_timeline(index, "le mail", now, 60)
    assert current.id == cur and len(ids) == 3 and "SIN-2026-07731" in text
    vision = ScriptedVisionModel(['{"segments": ["S2", "S9"], "reason": "mail"}'])
    kfs = pick_keyframes(vision, index, "remplis avec le mail", now=now, buffer_minutes=60)
    assert [k.frame.id for k in kfs] == [mail, cur]
    assert pick_keyframes(ScriptedVisionModel(['{"segments": []}']), index, "x", now=now, buffer_minutes=60) == []


def test_timeline_splits_same_window_new_content():
    from undo.analyzer.timeline import _segments
    from undo.models import Frame

    inbox = "Boîte Vinted Doctolib Maison du Lit Le Monde SNCF Freebox"
    news = Frame(ts=1, app="Mail", window_title="Reception", path="a", ocr_text=inbox + " COP31 forêts budget Sénat collectivités dotations escapades automne châteaux")
    news2 = Frame(ts=2, app="Mail", window_title="Reception", path="b", ocr_text=inbox + " COP31 forêts budget Sénat collectivités dotations escapades")
    order = Frame(ts=3, app="Mail", window_title="Reception", path="c", ocr_text=inbox + " commande MDL-20261018-4472 matelas Nuage 389,00 € Colis Express CE-77-4410-928 livraison")
    assert [len(s) for s in _segments([news, news2, order])] == [2, 1]


def test_timeline_splits_new_mail_in_list_layout():
    from undo.analyzer.timeline import _segments
    from undo.models import Frame

    chrome = " ".join(f"liste{i}" for i in range(250))
    a = Frame(ts=1, app="Mail", window_title="Reception", path="a", ocr_text=chrome + " " + " ".join(f"news{i}" for i in range(30)))
    b = Frame(ts=2, app="Mail", window_title="Reception", path="b", ocr_text=chrome + " " + " ".join(f"commande{i}" for i in range(30)))
    assert [len(s) for s in _segments([a, b])] == [1, 1]
