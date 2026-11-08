import time

from undo.recorder.index import fts_query_from_text
from tests.conftest import record_scene


def test_dedup_skips_identical_frames(recorder):
    cap, ocr, fg = recorder.fake
    cap.set(["hello world"])
    assert recorder.tick() is not None
    assert recorder.tick() is None  # identical
    cap.set(["something completely different", "with more lines", "and more"], bg="black")
    assert recorder.tick() is not None
    assert recorder.stats()["captured"] == 2
    assert recorder.stats()["skipped"] == 1


def test_identical_pixels_but_new_form_values_are_kept(recorder, monkeypatch):
    from undo import ax

    cap, ocr, fg = recorder.fake
    recorder.settings.ax = True
    state = {"v": "«Heure» = «10:30»"}
    monkeypatch.setattr(ax, "snapshot", lambda app, budget=0.5: [])
    monkeypatch.setattr(ax, "form_state", lambda controls: state["v"])
    cap.set(["form"])
    assert recorder.tick() is not None
    assert recorder.tick() is None
    state["v"] += "\n[x] «Tensiora»"
    f = recorder.tick()
    assert f is not None and "[x] «Tensiora»" in f.ax_text


def test_excluded_apps_are_not_recorded(recorder):
    cap, ocr, fg = recorder.fake
    fg.value = ("1Password", "Vault")
    assert recorder.tick() is None
    fg.value = ("Safari", "Trousseau d'accès - something")
    assert recorder.tick() is None
    assert recorder.index.count() == 0


def test_index_fts_search_and_purge(recorder):
    frames = record_scene(
        recorder,
        [
            (600, ["Nom: Dupont", "Adresse: 12 rue des Lilas", "Motif: renouvellement passeport"], ("Safari", "Dossier")),
            (300, ["Session expirée", "Veuillez recommencer"], ("Safari", "Dossier")),
            (10, ["Nom:", "Adresse:"], ("Safari", "Dossier")),
        ],
    )
    assert len(frames) == 3
    hits = recorder.index.search("j'ai perdu le formulaire avec l'adresse rue des Lilas")
    assert hits and hits[0][0].id == frames[0].id
    # time window filter
    assert recorder.index.between(time.time() - 400) and len(recorder.index.between(time.time() - 400)) == 2
    # purge: keep 7 minutes -> the 10-min-old frame disappears from db and disk
    recorder.settings.buffer_minutes = 7
    import os
    old_path = frames[0].path
    assert os.path.exists(old_path)
    assert recorder.purge() == 1
    assert not os.path.exists(old_path)
    assert recorder.index.count() == 2


def test_fts_query_strips_stopwords():
    q = fts_query_from_text("Je veux récupérer le texte du formulaire passeport")
    assert '"texte"*' in q and '"formulaire"*' in q and '"passeport"*' in q
    assert "veux" not in q and "récupérer" not in q


def test_pause_resume(recorder):
    recorder.pause("executor")
    recorder.pause("menubar")
    assert recorder.paused
    recorder.resume("executor")
    assert recorder.paused
    recorder.resume("menubar")
    assert not recorder.paused
