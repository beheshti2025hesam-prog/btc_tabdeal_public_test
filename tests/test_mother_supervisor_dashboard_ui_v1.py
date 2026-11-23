from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_mother_panel_exposes_supervisor_health_without_new_data_source():
    html = (ROOT / "web/dashboard.py").read_text(encoding="utf-8")
    for element_id in (
        "motherSupervisorStatus",
        "motherSupervisorWorkers",
        "motherSupervisorCircuits",
        "motherSupervisorLimits",
        "motherSupervisorAgents",
    ):
        assert f'id="{element_id}"' in html
    chat_panel = html.index('id="motherChatPanel"')
    supervisor_status = html.index('id="motherSupervisorStatus"')
    chat_login = html.index('id="motherChatLogin"')
    assert "Mother runtime supervisor health" in html
    assert chat_panel < supervisor_status < chat_login


def test_supervisor_ui_renders_circuit_and_worker_state_from_existing_mother_payload():
    js = (ROOT / "web/static/dashboard.js").read_text(encoding="utf-8")
    assert "function renderMotherSupervisor(j, failed=false)" in js
    assert "health.inflight_requests" in js
    assert "health.active_agents" in js
    assert "row.circuit" in js or "agents[name]?.circuit" in js
    assert "consecutive_failures" in js


def test_supervisor_ui_fails_closed_when_payload_is_missing_or_unsafe():
    js = (ROOT / "web/static/dashboard.js").read_text(encoding="utf-8")
    assert "renderMotherSupervisor(null,true)" in js
    assert "health.execution_authorized===true" in js
    assert "j?.execution_enabled===true" in js
    assert "j?.orders_placed===true" in js
    assert "j.specialist_supervisor===null" in js
    assert '"UNSAFE · BLOCKED"' in js
    assert '"DISABLED"' in js
