from undo.analyzer.analyzer import _normalize
from undo.models import Analysis


def test_normalize_common_slips():
    a = Analysis.model_validate(_normalize({
        "summary": "s", "before_state": "b", "recovered_content": {"Nom": "Dupont"},
        "strategy": "Manual Redo", "plan": "- click Nom\n- type Dupont", "confidence": 95, "target_app": None,
    }))
    assert a.strategy == "manual_redo" and a.confidence == 0.95
    assert a.plan == ["click Nom", "type Dupont"] and a.recovered_content == "Nom: Dupont" and a.target_app == ""


def test_extract_json_tolerates_non_breaking_spaces():
    import json
    from undo.analyzer.analyzer import _extract_json
    assert json.loads(_extract_json('{"plan":\u00a0 ["a"]}')) == {"plan": ["a"]}
