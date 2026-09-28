import tabdeal_futures_ws_test as collector


def test_persistent_mode_skips_git_checkpoint(monkeypatch):
    called = {"value": False}

    monkeypatch.setattr(collector, "GIT_CHECKPOINT_ENABLED", False)
    monkeypatch.setattr(
        collector,
        "git_checkpoint",
        lambda: called.__setitem__("value", True),
    )

    collector.maybe_checkpoint()

    assert called["value"] is False


def test_git_checkpoint_remains_enabled_by_default():
    assert collector.GIT_CHECKPOINT_ENABLED is True
