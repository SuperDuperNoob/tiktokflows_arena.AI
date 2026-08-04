"""
Compliance tests: regex obfuscation, banned-phrase detection, AI context check.
"""
import json

import caption_policy as cp
from compliance import ComplianceEngine

HYPE_OBFUSCATION = {
    "murah": "mughrahh",
    "harga": "hrga",
    "diskaun": "disqoun",
    "stok last": "stok las",
}


def test_hype_obfuscation_dictionary_present():
    # The plan's headline mapping murah -> mughrahh must exist.
    assert "mughrahh" in cp._PHONETIC["murah"]
    assert "hrga" in cp._PHONETIC["harga"]
    assert "disqoun" in cp._PHONETIC["diskaun"]


def test_obfuscation_removes_literal_keyword():
    out = cp.soften("murah gila hari ni", seed=7)
    assert out != "murah gila hari ni"
    # The literal keyword "murah" must no longer appear untouched.
    assert "murah" not in cp.find_hype(out) or not cp._HYPE_RE.search(out)


def test_obfuscation_mapping_deterministic():
    # Same word + seed always maps the same way.
    a = cp.obfuscate_word("murah", seed=42)
    b = cp.obfuscate_word("murah", seed=42)
    assert a == b
    # And it picks from the curated phonetic variants.
    assert a in cp._PHONETIC["murah"] or a != "murah"


def test_find_hype_detects_terms():
    hype = cp.find_hype("harga murah gila, stok last hari ini")
    assert "murah gila" in hype
    assert "harga" in hype
    assert "stok last" in hype


def test_medical_claim_is_prohibited():
    report = cp.scan_caption("ubat penawar migrain, hilangkan anxiety terus")
    assert report["needs_rewrite"] is True
    assert report["risk"] == "high"
    reasons = [w for _, w in report["prohibited"]]
    assert any(w.startswith("medical") for w in reasons)


def test_price_in_overlay_is_blocked():
    report = cp.scan_caption("harga RM39 je hari ini!")
    assert report["needs_rewrite"] is True
    reasons = [w for _, w in report["prohibited"]]
    assert any(w.startswith("price") for w in reasons)


def test_overclaim_is_blocked():
    report = cp.scan_caption("100% berkesan, terbaik di dunia")
    assert report["needs_rewrite"] is True


def test_medical_wording_gets_repaired():
    fixed, notes = cp.soften_claims("ubat kurus yang power")
    assert not cp.scan_caption(fixed)["needs_rewrite"]
    assert notes


def test_compliance_check_caption_regex_only():
    engine = ComplianceEngine({"strict_mode": True})
    ok, issues = engine.check_caption("sembuh migrain segera")
    assert ok is False
    assert issues
    ok2, _ = engine.check_caption("beg kuning bawah, murah je")
    assert ok2 is True


def test_process_caption_repairs_medical_but_keeps_obfuscated_hype():
    engine = ComplianceEngine({"strict_mode": True})
    final, ok, issues = engine.process_caption("ubat kurus, murah gila")
    assert ok is True  # repaired medical -> compliant
    assert not cp.scan_caption(final)["needs_rewrite"]


def test_process_caption_drops_unrepairable_price():
    engine = ComplianceEngine({"strict_mode": True})
    final, ok, issues = engine.process_caption("RM39 je hari ni")
    assert ok is False  # price cannot be repaired
    assert issues


# ---- AI context-aware layer (mocked) ----

def test_ai_layer_rewrites_non_compliant(monkeypatch):
    engine = ComplianceEngine({"strict_mode": True},
                              ai_config={"api_key": "k", "base_url": "https://x/v1"})
    assert engine._ai_available()

    class FakeResp:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": json.dumps({
                "is_compliant": False,
                "violations": ["hype but acceptable/evasion"],
                "rewritten_caption": "beg kuning bawah je murah",
            })}}]}

    def fake_post(url, **kw):
        assert url.startswith("https://x/v1")
        return FakeResp()

    monkeypatch.setattr("requests.post", fake_post)
    final, ok, issues = engine.process_caption("sesuatu yang melanggar")
    assert ok is True
    assert any("AI" in i or "rewrite" in i for i in issues)


def test_ai_layer_unavailable_falls_back_to_regex(monkeypatch):
    # No api_key -> AI off -> regex-only path still works.
    engine = ComplianceEngine({"strict_mode": True}, ai_config={})
    assert engine._ai_available() is False
    final, ok, issues = engine.process_caption("harga murah")
    assert ok is True
    assert final != "harga murah"  # obfuscated
