from pathlib import Path

MANIFEST = Path("docs/research/controlled_signal_research_v1_evidence_manifest.md").read_text()

def test_manifest_pins_prior_evidence():
    for phrase in [
        "36489452534",
        "11000741523",
        "2d6417289b3ddbc5befb622f8e64d1259dd6eea73a7c24d6abc37e64de85addc",
        "1049",
        "14 at 5 bps transaction + 2 bps slippage per side",
    ]:
        assert phrase in MANIFEST

def test_manifest_forbids_feature_substitution():
    assert "It is **not** a feature snapshot." in MANIFEST
    assert "must NOT run against this artifact" in MANIFEST
    assert "CSRv1-A remains **specified but unevaluated**." in MANIFEST
