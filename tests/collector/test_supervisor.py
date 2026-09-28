import scripts.collector_supervisor as supervisor


class FakeChild:
    def __init__(self, return_code=1):
        self.pid = 4242
        self.return_code = return_code
        self.terminated = False

    def wait(self):
        supervisor.stopping = True
        return self.return_code

    def poll(self):
        return None if not self.terminated else self.return_code

    def terminate(self):
        self.terminated = True


def test_supervisor_forces_persistent_environment(monkeypatch, tmp_path):
    collector = tmp_path / "tabdeal_futures_ws_test.py"
    collector.write_text("# test collector\\n", encoding="utf-8")
    monkeypatch.setattr(supervisor, "COLLECTOR", collector)
    monkeypatch.setattr(supervisor, "STATE_DIR", tmp_path / "runtime")
    monkeypatch.setattr(supervisor, "STATE_FILE", tmp_path / "runtime" / "state.json")
    monkeypatch.setattr(supervisor, "stopping", False)
    monkeypatch.setattr(supervisor.signal, "signal", lambda *args: None)
    monkeypatch.setenv("COLLECTOR_RUN_SECONDS", "19200")
    monkeypatch.setenv("HES_COLLECTOR_GIT_CHECKPOINT", "1")

    captured = {}

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs["env"]
        return FakeChild()

    monkeypatch.setattr(supervisor.subprocess, "Popen", fake_popen)

    assert supervisor.main() == 0
    assert captured["env"]["HES_COLLECTOR_MODE"] == "persistent-vps"
    assert captured["env"]["HES_COLLECTOR_GIT_CHECKPOINT"] == "0"
    assert "COLLECTOR_RUN_SECONDS" not in captured["env"]
    assert captured["command"][-1] == str(collector)


def test_supervisor_restarts_after_child_exit(monkeypatch, tmp_path):
    collector = tmp_path / "tabdeal_futures_ws_test.py"
    collector.write_text("# test collector\\n", encoding="utf-8")
    monkeypatch.setattr(supervisor, "COLLECTOR", collector)
    monkeypatch.setattr(supervisor, "STATE_DIR", tmp_path / "runtime")
    monkeypatch.setattr(supervisor, "STATE_FILE", tmp_path / "runtime" / "state.json")
    monkeypatch.setattr(supervisor, "RESTART_DELAY_SECONDS", 0)
    monkeypatch.setattr(supervisor.signal, "signal", lambda *args: None)
    monkeypatch.setattr(supervisor, "stopping", False)

    children = []

    def fake_popen(command, **kwargs):
        child = FakeChild()
        children.append(child)
        if len(children) >= 2:
            original_wait = child.wait
            def stop_after_wait():
                code = original_wait()
                supervisor.stopping = True
                return code
            child.wait = stop_after_wait
        return child

    monkeypatch.setattr(supervisor.subprocess, "Popen", fake_popen)

    assert supervisor.main() == 0
    assert len(children) == 2
    assert all(child.return_code == 1 for child in children)
