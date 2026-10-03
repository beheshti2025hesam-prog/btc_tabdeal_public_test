import subprocess

import scripts.collector_supervisor as supervisor


class FakeChild:
    def __init__(self, stop_on_wait=True, return_code=1):
        self.pid = 4242
        self.return_code = return_code
        self.stop_on_wait = stop_on_wait
        self.terminated = False
        self.killed = False

    def wait(self, timeout=None):
        if self.stop_on_wait:
            supervisor.stopping = True
        return self.return_code

    def poll(self):
        return self.return_code if (self.terminated or self.killed) else None

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


class HungChild(FakeChild):
    def __init__(self):
        super().__init__(stop_on_wait=False)

    def wait(self, timeout=None):
        if self.killed:
            return self.return_code
        if timeout is not None:
            raise subprocess.TimeoutExpired(cmd="collector", timeout=timeout)
        return self.return_code


def test_supervisor_forces_persistent_environment(monkeypatch, tmp_path):
    collector = tmp_path / "tabdeal_futures_ws_test.py"
    collector.write_text("# test collector\n", encoding="utf-8")
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
    collector.write_text("# test collector\n", encoding="utf-8")
    monkeypatch.setattr(supervisor, "COLLECTOR", collector)
    monkeypatch.setattr(supervisor, "STATE_DIR", tmp_path / "runtime")
    monkeypatch.setattr(supervisor, "STATE_FILE", tmp_path / "runtime" / "state.json")
    monkeypatch.setattr(supervisor, "RESTART_DELAY_SECONDS", 0)
    monkeypatch.setattr(supervisor.signal, "signal", lambda *args: None)
    monkeypatch.setattr(supervisor, "stopping", False)

    children = []

    def fake_popen(command, **kwargs):
        child = FakeChild(stop_on_wait=len(children) >= 1)
        children.append(child)
        return child

    monkeypatch.setattr(supervisor.subprocess, "Popen", fake_popen)

    assert supervisor.main() == 0
    assert len(children) == 2
    assert all(child.return_code == 1 for child in children)


def test_stop_child_kills_if_sigterm_does_not_exit(monkeypatch, tmp_path):
    monkeypatch.setattr(supervisor, "STATE_DIR", tmp_path / "runtime")
    monkeypatch.setattr(supervisor, "STATE_FILE", tmp_path / "runtime" / "state.json")
    monkeypatch.setattr(supervisor, "STOP_GRACE_SECONDS", 0.01)

    hung = HungChild()
    monkeypatch.setattr(supervisor, "child", hung)

    supervisor.stop_child()

    assert hung.terminated is True
    assert hung.killed is True
    state = supervisor.STATE_FILE.read_text(encoding="utf-8")
    assert "collector_kill_after_sigterm_timeout" in state
