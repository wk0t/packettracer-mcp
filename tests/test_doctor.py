import asyncio
import json
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import doctor


@pytest.fixture
def installed(tmp_path,monkeypatch):
    root = tmp_path/"installed connector"
    root.mkdir()
    cisco = tmp_path/"Cisco Packet Tracer"
    (cisco/"bin").mkdir(parents=True)
    (cisco/"bin/PacketTracer.exe").write_bytes(b"placeholder")
    for leaf in ("server.py","coursework.py","windows_ui.py","install.py"):
        (root/leaf).write_text("# fixture\n",encoding="utf-8")
    (root/"requirements.txt").write_text("fixture-package==1.0\n",encoding="utf-8")
    (root/"vendor").mkdir()
    (root/"vendor/pktctl.exe").write_bytes(b"placeholder")
    (root/".venv/Scripts").mkdir(parents=True)
    (root/".venv/Scripts/python.exe").write_bytes(b"placeholder")
    (root/"registration").mkdir()
    (root/"registration/packettracer-mcp.pta").write_bytes(b"placeholder")
    path = root/"settings.json"
    path.write_text(json.dumps({"app_id":"local.packettracer.mcp","secret":"never-display-this-value",
        "downloads":str(tmp_path/"Downloads"),"workspace":str(tmp_path/"Work"),
        "packet_tracer_home":str(cisco),"address":"127.0.0.1:39000"}),encoding="utf-8-sig")
    (root/"mcp-config.json").write_text(json.dumps({"mcpServers":{"packettracer":{
        "command":str(root/".venv/Scripts/python.exe"),"args":[str(root/"server.py"),"--settings",str(path)]}}}),encoding="utf-8")
    monkeypatch.setattr(doctor.metadata,"version",lambda package:"1.0")
    monkeypatch.setattr(doctor.subprocess,"run",lambda *args,**kwargs:subprocess.CompletedProcess(args[0],0,stdout="pktctl 0.2.2\n"))
    return root,path


def test_offline_check_does_not_probe_simulator_or_create_files(installed,monkeypatch):
    root,path = installed
    before = {str(p):p.read_bytes() for p in root.rglob("*") if p.is_file()}
    async def forbidden(*args):
        pytest.fail("Offline diagnostics must not start an MCP session")
    monkeypatch.setattr(doctor,"probe_client",forbidden)
    report,code = asyncio.run(doctor.diagnose(path,offline=True))
    assert code == 0 and report["status"] == "ready" and report["mode"] == "offline"
    assert {str(p):p.read_bytes() for p in root.rglob("*") if p.is_file()} == before
    assert not any(p.name in {"Downloads","Work"} for p in root.parent.iterdir())
    assert "never-display-this-value" not in doctor.render_report(report,as_json=True)


def test_missing_engine_is_broken_and_never_probed(installed,monkeypatch):
    root,path = installed
    (root/"vendor/pktctl.exe").unlink()
    async def forbidden(*args): pytest.fail("Broken installations must not start MCP")
    monkeypatch.setattr(doctor,"probe_client",forbidden)
    report,code = asyncio.run(doctor.diagnose(path))
    assert code == 1 and report["status"] == "error"
    assert any(c["name"] == "engine" and c["status"] == "fail" for c in report["checks"])


@pytest.mark.parametrize("connected,expected_status,expected_code",[(True,"ready",0),(False,"attention",2)])
def test_live_check_distinguishes_healthy_mcp_from_cisco_state(installed,monkeypatch,connected,expected_status,expected_code):
    _,path = installed
    async def probe(*args):
        return {"tools":87,"packet_tracer":{"connected":connected,"problem":"Open Cisco and register the application"}}
    monkeypatch.setattr(doctor,"probe_client",probe)
    report,code = asyncio.run(doctor.diagnose(path))
    assert report["status"] == expected_status and code == expected_code
    assert any(c["name"] == "mcp" and c["status"] == "pass" for c in report["checks"])


def test_wrong_tool_count_is_not_reported_ready(installed,monkeypatch):
    _,path = installed
    async def probe(*args): return {"tools":1,"packet_tracer":{"connected":True}}
    monkeypatch.setattr(doctor,"probe_client",probe)
    report,code = asyncio.run(doctor.diagnose(path))
    assert code == 1 and report["status"] == "error"


def test_timeout_returns_actionable_failure_without_secret(installed,monkeypatch):
    _,path = installed
    async def probe(*args): raise TimeoutError("never-display-this-value")
    monkeypatch.setattr(doctor,"probe_client",probe)
    report,code = asyncio.run(doctor.diagnose(path))
    assert code == 1 and any(c.get("action") for c in report["checks"] if c["status"] == "fail")
    assert "never-display-this-value" not in doctor.render_report(report,as_json=True)


@pytest.mark.parametrize("change",["invalid-json","overlapping-roots","missing-secret","dependency-version","broken-client-config"])
def test_invalid_installation_has_a_clear_failure(installed,monkeypatch,change):
    root,path = installed
    settings = json.loads(path.read_text(encoding="utf-8-sig"))
    if change == "invalid-json": path.write_text("{broken",encoding="utf-8")
    elif change == "overlapping-roots":
        settings["workspace"] = settings["downloads"]
        path.write_text(json.dumps(settings))
    elif change == "missing-secret":
        del settings["secret"]
        path.write_text(json.dumps(settings))
    elif change == "dependency-version": monkeypatch.setattr(doctor.metadata,"version",lambda package:"0.0")
    else: (root/"mcp-config.json").write_text("{}")
    report,code = asyncio.run(doctor.diagnose(path,offline=True))
    assert code == 1 and report["status"] == "error"
    assert any(c["status"] == "fail" and c.get("action") for c in report["checks"])


def test_human_report_lists_next_action(installed,monkeypatch):
    _,path = installed
    async def probe(*args): return {"tools":87,"packet_tracer":{"connected":False}}
    monkeypatch.setattr(doctor,"probe_client",probe)
    report,_ = asyncio.run(doctor.diagnose(path))
    output = doctor.render_report(report)
    assert "ATTENTION" in output and "87" in output
    assert "Extensions" in output and "never-display-this-value" not in output


@pytest.mark.parametrize("value",[39000,"127.0.0.1:0","127.0.0.1:65536"])
def test_invalid_endpoint_is_rejected_offline(installed,value):
    _,path = installed
    settings = json.loads(path.read_text(encoding="utf-8-sig"))
    settings["address"] = value
    path.write_text(json.dumps(settings),encoding="utf-8")
    report,code = asyncio.run(doctor.diagnose(path,offline=True))
    assert code == 1
    assert any(c["name"] == "settings" and c["status"] == "fail" for c in report["checks"])


@pytest.mark.parametrize("change",["missing-settings","other-settings","wrong-interpreter","wrong-server"])
def test_stale_client_fragment_cannot_report_ready(installed,monkeypatch,change):
    root,path = installed
    config_path = root/"mcp-config.json"
    config = json.loads(config_path.read_text())
    entry = config["mcpServers"]["packettracer"]
    if change == "missing-settings":
        entry["args"] = entry["args"][:1]
    elif change == "other-settings":
        other = root/"other-settings.json"
        other.write_bytes(path.read_bytes())
        entry["args"][2] = str(other)
    elif change == "wrong-interpreter":
        entry["command"] = sys.executable
    else:
        other = root/"other-server.py"
        other.write_text("# other server")
        entry["args"][0] = str(other)
    config_path.write_text(json.dumps(config),encoding="utf-8")
    async def forbidden(*args): pytest.fail("An invalid client entry must not be probed")
    monkeypatch.setattr(doctor,"probe_client",forbidden)
    report,code = asyncio.run(doctor.diagnose(path))
    assert code == 1
    assert any(c["name"] == "client_fragment" and c["status"] == "fail" for c in report["checks"])
