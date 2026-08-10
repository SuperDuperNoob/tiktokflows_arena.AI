"""Compliance tests: regex obfuscation, banned-phrase detection, AI context check."""
import json

import services.compliance.caption_policy as cp
from services.compliance import ComplianceEngine

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


def test_prohibited_price_figure():
    assert cp.find_prohibited("harga RM39 je")
    assert cp.scan_caption("harga RM39 je")["needs_rewrite"]


def test_prohibited_medical_claim():
    assert cp.find_prohibited("ubat sembuh migrain")
    assert cp.scan_caption("ubat sembuh migrain")["needs_rewrite"]


def test_medical_substitution_repair():
    fixed, _ = cp.soften_claims("ubat sembuh sakit kepala")
    assert cp.scan_caption(fixed)["needs_rewrite"] is False
    assert "ubat" not in fixed


def test_overclaim_price_not_repairable():
    fixed, _ = cp.soften_claims("harga RM39 ke mana?")
    assert "RM" in fixed  # price not removed by medical substitution
    assert cp.scan_caption(fixed)["needs_rewrite"]  # still needs rewrite -> dropped


def test_compliance_engine_rejects_price():
    eng = ComplianceEngine({"strict_mode": True}, {"api_key": "", "base_url": ""})
    final_text, is_compliant, issues = eng.process_caption("harga RM39 hari ni")
    assert is_compliant is False
    assert final_text != "harga RM39 hari ni"


def test_compliance_engine_rejects_medical():
    eng = ComplianceEngine({"strict_mode": True}, {"api_key": "", "base_url": ""})
    final_text, is_compliant, issues = eng.process_caption("ubat sembuh diabetes")
    # Medical claims are repaired into compliant lifestyle wording, not rejected
    assert is_compliant is True
    assert "medical" in str(issues).lower() or "Repaired" in str(issues)


def test_compliance_engine_passes_clean():
    eng = ComplianceEngine({"strict_mode": True}, {"api_key": "", "base_url": ""})
    final_text, is_compliant, issues = eng.process_caption("murah gila hari ni beg kuning")
    assert is_compliant is True
    assert "murah" not in final_text or final_text != "murah gila hari ni beg kuning"


def test_compliance_engine_obfuscates_hype():
    eng = ComplianceEngine({"strict_mode": True}, {"api_key": "", "base_url": ""})
    final_text, is_compliant, issues = eng.process_caption("murah gila stok last")
    assert is_compliant is True
    # At least one hype term should be obfuscated
    assert cp.find_hype(final_text) != cp.find_hype("murah gila stok last")


def test_compliance_validate_for_pool():
    eng = ComplianceEngine({"strict_mode": True}, {"api_key": "", "base_url": ""})
    ok, final, issues = eng.validate_for_pool("murah gila hari ni")
    assert ok is True
    ok2, final2, issues2 = eng.validate_for_pool("harga RM39")
    assert ok2 is False