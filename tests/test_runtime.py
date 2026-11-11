"""Client-neutral settings selection and startup configuration."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


def settings_file(root):
    root.mkdir(parents=True)
    path = root / "settings.json"
    path.write_text(json.dumps({"app_id":"local.packettracer.mcp", "secret":"test-only-secret",
        "downloads":str(root/"downloads"), "workspace":str(root/"workspace"),
        "packet_tracer_home":str(root/"cisco")}),encoding="utf-8")
    return path


def test_explicit_settings_select_runtime_from_config_directory(tmp_path,monkeypatch):
    path = settings_file(tmp_path/"custom installation")
    monkeypatch.chdir(tmp_path)
    selected, runtime, settings = server.load_runtime(str(path))
    assert selected == path.resolve()
    assert runtime == path.parent.resolve()
    assert settings["app_id"] == "local.packettracer.mcp"


def test_explicit_settings_override_environment(tmp_path,monkeypatch):
    chosen = settings_file(tmp_path/"chosen")
    ignored = settings_file(tmp_path/"ignored")
    monkeypatch.setenv("PACKETTRACER_MCP_SETTINGS",str(ignored))
    selected, _, _ = server.load_runtime(chosen)
    assert selected == chosen


def test_environment_settings_work_outside_installation(tmp_path,monkeypatch):
    path = settings_file(tmp_path/"custom")
    monkeypatch.setenv("PACKETTRACER_MCP_SETTINGS",str(path))
    monkeypatch.chdir(tmp_path)
    selected, runtime, _ = server.load_runtime()
    assert selected == path and runtime == path.parent


def test_default_finds_config_beside_installed_server(tmp_path,monkeypatch):
    path = settings_file(tmp_path/"installed")
    monkeypatch.delenv("PACKETTRACER_MCP_SETTINGS",raising=False)
    monkeypatch.setattr(server,"ROOT",path.parent)
    assert server.load_runtime()[0] == path


def test_checkout_uses_neutral_default_when_no_local_config(tmp_path,monkeypatch):
    path = settings_file(tmp_path/"neutral")
    monkeypatch.delenv("PACKETTRACER_MCP_SETTINGS",raising=False)
    monkeypatch.setattr(server,"ROOT",tmp_path/"checkout")
    monkeypatch.setattr(server,"default_install_root",lambda:path.parent)
    assert server.load_runtime()[0] == path


def test_optional_runtime_dir_can_separate_settings_and_engine(tmp_path):
    path = settings_file(tmp_path/"configuration")
    selected, runtime, _ = server.load_runtime(path,tmp_path/"binary")
    assert selected == path and runtime == (tmp_path/"binary").resolve()


def test_invalid_settings_report_field_without_credential_contents(tmp_path):
    path = settings_file(tmp_path/"invalid")
    data = json.loads(path.read_text())
    data["downloads"] = None
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError,match="downloads") as failure:
        server.load_runtime(path)
    assert "test-only-secret" not in str(failure.value)


def test_cli_help_needs_no_client_or_settings_file(tmp_path):
    response = subprocess.run([sys.executable,str(Path(server.__file__).resolve()),"--help"],
                              cwd=tmp_path,capture_output=True,text=True,timeout=20)
    assert response.returncode == 0
    assert "--settings" in response.stdout
    assert "--runtime-dir" in response.stdout
    assert not response.stderr
