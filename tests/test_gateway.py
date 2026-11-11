"""Exercise the real gateway against a stateful in-memory Packet Tracer engine.

The fake models the native engine's file effects, rather than merely asserting
that mocks were called. Live IPC coverage is supplied by the integration test.
"""
import asyncio
from datetime import timedelta
import json
from pathlib import Path
import sys

import pytest
from mcp import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import Gateway, PKT_ONLY


def result(value=None, *, error=False, text=None):
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text if text is not None else json.dumps(value))],
        structuredContent=value,
        isError=error,
    )


class MemoryEngine:
    def __init__(self, current="", content=b"unsaved network"):
        self.current = str(current)
        self.content = content
        self.calls = []
        self.timeouts = []
        self.responses = {}

    def _save(self, path):
        target = Path(path)
        target.write_bytes(self.content)
        self.current = str(target)
        return {"path": self.current, "bytes": len(self.content)}

    async def call_tool(self, name, arguments, **kwargs):
        timeout = kwargs.get("read_timeout_seconds")
        assert isinstance(timeout, timedelta), "The MCP SDK requires a datetime.timedelta timeout."
        self.timeouts.append(timeout)
        args = dict(arguments)
        self.calls.append((name, args))
        if name in self.responses:
            return self.responses[name]
        if name == "call_ipc":
            return result({"call": "appWindow.getActiveFile().getSavedFilename()", "returns": "QString", "value": self.current})
        if name == "save_network":
            return result(self._save(args["path"]))
        if name in {"open_network", "new_network"}:
            saved = self._save(args["save_current_to"]) if args.get("save_current_to") else None
            if name == "open_network":
                target = Path(args["path"])
                self.current = str(target)
                self.content = target.read_bytes()
                return result({"path": self.current, "devices": 2, "saved_previous": saved})
            self.current = ""
            self.content = b"empty network"
            return result({"cleared": True, "saved_previous": saved})
        return result({"tool": name})


@pytest.fixture
def make_gateway(tmp_path):
    downloads = tmp_path / "Téléchargements"
    workspace = tmp_path / "TP"
    downloads.mkdir()
    workspace.mkdir()

    def create(current="", content=b"unsaved network"):
        engine = MemoryEngine(current, content)
        gateway = Gateway({"downloads": str(downloads), "workspace": str(workspace)}, engine)
        writable = {"open_network", "new_network", "save_network", "add_device", "configure_ios", "call_ipc", *PKT_ONLY}
        gateway.native = {
            name: types.Tool(name=name, inputSchema={"type": "object"},
                             annotations=types.ToolAnnotations(readOnlyHint=name not in writable))
            for name in writable | {"status", "run_cli", "screenshot", "list_ports"}
        }
        return gateway, engine

    return create


def test_open_downloaded_activity_copies_source_and_preserves_unsaved_network(make_gateway):
    gateway, engine = make_gateway(content=b"valuable unsaved changes")
    source = gateway.files.downloads / "TP IPv6.pka"
    source.write_bytes(b"teacher activity\x00\xff")
    opened = asyncio.run(gateway.call("open_network", {"path": str(source)}))
    assert not opened.isError
    actual = Path(opened.structuredContent["path"])
    assert actual != source
    assert actual.is_relative_to(gateway.files.workspace)
    assert engine.content == source.read_bytes() == b"teacher activity\x00\xff"
    assert source.read_bytes() == b"teacher activity\x00\xff"
    saved = opened.structuredContent["saved_previous"]
    assert Path(saved["path"]).read_bytes() == b"valuable unsaved changes"


def test_new_network_keeps_pka_backup_and_overrides_unsafe_backup_argument(make_gateway):
    gateway, engine = make_gateway(content=b"ongoing pka work")
    source = gateway.files.downloads / "original.pka"
    source.write_bytes(b"original")
    engine.current = str(source)
    reply = asyncio.run(gateway.call("new_network", {"save_current_to": str(source)}))
    saved = Path(reply.structuredContent["saved_previous"]["path"])
    assert saved.suffix == ".pka"
    assert saved.is_relative_to(gateway.files.workspace)
    assert saved.read_bytes() == b"ongoing pka work"
    assert source.read_bytes() == b"original"
    assert engine.current == ""
    assert engine.content == b"empty network"


@pytest.mark.parametrize("explicit", [False, True])
def test_save_cannot_overwrite_downloaded_source(make_gateway, explicit):
    gateway, engine = make_gateway(content=b"student changes")
    source = gateway.files.downloads / "original.pka"
    source.write_bytes(b"teacher original")
    engine.current = str(source)
    args = {"path": str(source)} if explicit else {}
    with pytest.raises(ValueError, match="working directory"):
        asyncio.run(gateway.call("save_network", args))
    assert source.read_bytes() == b"teacher original"
    assert not any(name == "save_network" for name, _ in engine.calls)


def test_save_keeps_existing_working_file_as_backup_before_replacing(make_gateway):
    gateway, engine = make_gateway(content=b"new student configuration")
    target = gateway.files.workspace / "rendu.pka"
    target.write_bytes(b"previous saved configuration")
    reply = asyncio.run(gateway.call("save_network", {"path": str(target)}))
    assert not reply.isError
    assert target.read_bytes() == b"new student configuration"
    backups = list((gateway.files.workspace / "sauvegardes").glob("*.pka"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"previous saved configuration"


def test_save_unsaved_network_chooses_new_safe_path(make_gateway):
    gateway, engine = make_gateway(content=b"new topology")
    reply = asyncio.run(gateway.call("save_network", {}))
    target = Path(reply.structuredContent["path"])
    assert target.is_relative_to(gateway.files.workspace)
    assert target.suffix == ".pkt"
    assert target.read_bytes() == b"new topology"


@pytest.mark.parametrize("tool", sorted(PKT_ONLY))
def test_pkt_snapshot_operations_reject_pka_before_reaching_engine(make_gateway, tool):
    gateway, engine = make_gateway(current="activity.pka")
    with pytest.raises(ValueError, match=".pka activities"):
        asyncio.run(gateway.call(tool, {}))
    assert all(name == "call_ipc" for name, _ in engine.calls)


def test_mutation_of_manually_opened_source_first_saves_working_copy(make_gateway):
    gateway, engine = make_gateway(content=b"current unsaved source work")
    source = gateway.files.downloads / "manually-opened.pkt"
    source.write_bytes(b"unchanged source")
    engine.current = str(source)
    asyncio.run(gateway.call("add_device", {"model": "PC-PT"}))
    assert Path(engine.current).is_relative_to(gateway.files.workspace)
    assert Path(engine.current).read_bytes() == b"current unsaved source work"
    assert source.read_bytes() == b"unchanged source"
    assert [name for name, _ in engine.calls] == ["call_ipc", "call_ipc", "save_network", "add_device"]


def test_native_result_is_preserved_with_images_metadata_and_structured_content(make_gateway):
    gateway, engine = make_gateway()
    reply = types.CallToolResult(
        content=[types.ImageContent(type="image", data="cG5n", mimeType="image/png"),
                 types.TextContent(type="text", text="actual engine output")],
        structuredContent={"saved_to": "proof.png"},
        _meta={"trace": "engine-original"},
        isError=False,
    )
    engine.responses["screenshot"] = reply
    forwarded = asyncio.run(gateway.call("screenshot", {}))
    assert forwarded is reply
    assert forwarded.model_dump() == reply.model_dump()
    assert engine.timeouts == [timedelta(seconds=150)]


def test_engine_error_and_incomplete_configuration_are_not_changed_to_success(make_gateway):
    gateway, engine = make_gateway()
    failed = result(error=True, text="device R404 does not exist")
    engine.responses["run_cli"] = failed
    assert asyncio.run(gateway.call("run_cli", {"device": "R404", "command": "show version"})) is failed
    partial = result({"completed": False, "applied": 1, "total": 2,
                      "results": [{"command": "bad command", "status": "invalid"}]})
    engine.responses["configure_ios"] = partial
    assert asyncio.run(gateway.call("configure_ios", {"device": "R1", "commands": ["bad command"]})) is partial
    assert partial.structuredContent["completed"] is False


def test_error_during_pre_save_prevents_open_and_is_returned_unchanged(make_gateway):
    gateway, engine = make_gateway(content=b"valuable current work")
    source = gateway.files.downloads / "tp.pkt"
    source.write_bytes(b"other topology")
    failed = result(error=True, text="could not save previous network")
    engine.responses["open_network"] = failed
    assert asyncio.run(gateway.call("open_network", {"path": str(source)})) is failed
    assert engine.content == b"valuable current work"
    assert engine.current == ""


def test_data_accepts_json_text_and_raises_for_native_error(make_gateway):
    gateway, engine = make_gateway()
    engine.responses["status"] = result(text='{"connected":true}')
    assert asyncio.run(gateway.data("status", {})) == {"connected": True}
    engine.responses["status"] = result(error=True, text="IPC unavailable")
    with pytest.raises(RuntimeError, match="IPC unavailable"):
        asyncio.run(gateway.data("status", {}))
