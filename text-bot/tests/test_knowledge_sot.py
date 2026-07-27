from ava_client import _merge_knowledge


def test_merge_prefers_brain_as_sot():
    out = _merge_knowledge(
        {"ok": True, "topic": "x", "topic_id": "overview", "text": "LEGACY ONLY", "matches": [{"id": "l"}]},
        {"ok": True, "text": "BRAIN HIT", "matches": [{"id": "b"}]},
    )
    assert out["text"].startswith("BRAIN HIT")
    assert "Legacy FAQ" in out["text"]
    assert out["source"] == "brain+legacy"
    assert out["source_of_truth"] == "second_brain"
    assert out["matches"][0]["id"] == "b"


def test_merge_brain_only():
    out = _merge_knowledge(
        {"ok": False, "text": ""},
        {"ok": True, "text": "BRAIN", "matches": []},
    )
    assert out["text"] == "BRAIN"
    assert out["source"] == "brain"
