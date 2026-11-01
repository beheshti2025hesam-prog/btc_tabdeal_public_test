from __future__ import annotations

import importlib.util
from pathlib import Path


def test_code_root_follows_current_release_symlink(tmp_path, monkeypatch):
    release = tmp_path / "releases" / "release-a"
    scripts = release / "scripts"
    scripts.mkdir(parents=True)
    helper = scripts / "runtime_paths_v1.py"
    helper.write_text(
        "from pathlib import Path\\nimport os\\n"
        "CODE_ROOT = Path(__file__).resolve().parents[1]\\n"
        "DATA_ROOT = Path(os.environ.get('HES_DATA_ROOT', '/opt/hes-trade-agent')).expanduser().resolve()\\n",
        encoding="utf-8",
    )
    current = tmp_path / "current"
    current.symlink_to(release, target_is_directory=True)
    shared_data = tmp_path / "shared-data"
    monkeypatch.setenv("HES_DATA_ROOT", str(shared_data))
    spec = importlib.util.spec_from_file_location("hes_runtime_paths_test", current / "scripts" / "runtime_paths_v1.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    assert module.CODE_ROOT == release.resolve()
    assert module.DATA_ROOT == shared_data.resolve()
