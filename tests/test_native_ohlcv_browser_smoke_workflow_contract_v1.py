from pathlib import Path


def test_browser_smoke_workflow_creates_ephemeral_mother_chat_token():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/native-ohlcv-browser-render-smoke-v1.yml").read_text()

    fixture_step = workflow.index("Prepare fresh persisted Gate.io fixtures")
    token_step = workflow.index("Create ephemeral local Mother chat token")
    dashboard_step = workflow.index("Start read-only dashboard")
    assert fixture_step < token_step < dashboard_step
    assert "secrets.token_urlsafe(48)" in workflow
    assert "chmod 600 /tmp/hes-mother-chat-token" in workflow
    assert 'echo "::add-mask::$token"' in workflow
    assert 'HES_MOTHER_CHAT_TOKEN_FILE=/tmp/hes-mother-chat-token' in workflow
    assert 'HES_MOTHER_CHAT_TOKEN=$token' in workflow
