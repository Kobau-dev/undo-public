import re

from undo.i18n import FR, t


def test_english_is_the_default(monkeypatch):
    monkeypatch.delenv("UNDO_LANG", raising=False)
    assert t("Done") == "Done"
    assert t("{n} values restored from history", n=3) == "3 values restored from history"


def test_undo_lang_fr_switches_to_french(monkeypatch):
    monkeypatch.setenv("UNDO_LANG", "fr")
    assert t("Done") == "Terminé"
    assert t("{n} values restored from history", n=3) == "3 valeurs remises depuis l'historique"
    assert t("Not translated") == "Not translated"


def test_translations_keep_their_placeholders():
    for en, fr in FR.items():
        assert sorted(re.findall(r"{(\w+)}", en)) == sorted(re.findall(r"{(\w+)}", fr)), en
