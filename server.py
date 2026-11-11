"""MCP stdio gateway: pktctl's complete IPC API plus local course tools."""
from __future__ import annotations

import asyncio
import base64
from contextlib import AsyncExitStack
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from coursework import LabFiles, plan_vlsm

ROOT = Path(__file__).resolve().parent
INSTRUCTIONS = """Control Cisco Packet Tracer and complete course labs. Start with tp_lister and
tp_lire, then tp_preparer and open_network using working_file. Read activity_instructions
and the topology before making changes. Follow the lab addresses, names and steps.
Check configure_ios.completed, run_cli.finished and status, and inspect actual outputs.
Never invent a successful ping or a score. Do not guess the author password.
Save and produce a verification report. Use describe_ipc, then call_ipc to access
additional Cisco API methods. Advanced tools that rewrite a .pkt reject .pka
activities to preserve their container.
"""


def definition(name, description, properties=None, required=(), read_only=True):
    return types.Tool(name=name, description=description, inputSchema={
        "type": "object", "properties": properties or {}, "required": list(required),
        "additionalProperties": False,
    }, annotations=types.ToolAnnotations(readOnlyHint=read_only, openWorldHint=False))


STRING = {"type": "string"}
LOCAL_TOOLS = [
    definition("tp_lister", "Find .pka/.pkt labs and PDF/Word instructions in Downloads and working copies.",
               {"query": STRING, "limit": {"type": "integer", "minimum": 1, "maximum": 500}}),
    definition("tp_lire", "Read PDF/Word/text instructions, including tables. Paginate using offset; report scanned PDFs.",
               {"path": STRING, "offset": {"type": "integer", "minimum": 0}, "max_chars": {"type": "integer", "minimum": 1,"maximum": 100000}}, ["path"]),
    definition("tp_preparer", "Copy a .pka/.pkt into a unique working directory; return working_file to open. Preserve the original and its SHA256.",
               {"path": STRING}, ["path"], False),
    definition("tp_rapport", "Save a Markdown report of steps, commands, evidence, results and limitations in the working directory.",
               {"path": STRING, "content": STRING, "overwrite": {"type": "boolean"}}, ["path", "content"], False),
    definition("tp_vlsm", "Calculate and validate a non-overlapping IPv4 VLSM plan (LAN convention: exclude network/broadcast addresses, minimum /30).",
               {"network": STRING, "lans": {"type": "array", "items": {"type": "object", "properties": {"name": STRING, "hosts": {"type":"integer","minimum":1}}, "required":["name","hosts"], "additionalProperties":False}}}, ["network","lans"]),
    definition("tp_diagnostic", "Check connector status, engine version, directories and the live connection to Packet Tracer."),
    definition("tp_demarrer", "Open Packet Tracer installed on this PC, then call status to verify the connection.", read_only=False),
]

WINDOW_ID = {"type":"integer", "minimum":1}
UI_TOOLS = [
    definition("ui_windows", "List Cisco Packet Tracer windows, including dialogs. Use the returned window_id values."),
    definition("ui_inspect", "Read the elements and focus of a Cisco window before interacting. Repeat after each action.",
               {"window_id":WINDOW_ID,"max_nodes":{"type":"integer","minimum":1,"maximum":300}},["window_id"]),
    definition("ui_screenshot", "View a verified Cisco window as a PNG for features without an API. Reject black captures; do not capture the desktop.",
               {"window_id":WINDOW_ID},["window_id"]),
    definition("ui_click", "Click in Cisco after a recent observation, using relative coordinates. Right-click and double-click are available.",
               {"window_id":WINDOW_ID,"x":{"type":"integer","minimum":0},"y":{"type":"integer","minimum":0},"mouse_button":{"enum":["left","right","middle"]},"click_count":{"enum":[1,2]}},["window_id","x","y"],False),
    definition("ui_type_text", "Type literal text in Cisco. Check the field and focus immediately beforehand. Return the state after typing.",
               {"window_id":WINDOW_ID,"text":STRING},["window_id","text"],False),
    definition("ui_press_keys", "Send a simple key chord to Cisco: CTRL+SHIFT+C, ENTER, TAB, ESC, ALT+F4... Return the new state.",
               {"window_id":WINDOW_ID,"keys":STRING},["window_id","keys"],False),
    definition("ui_drag", "Drag an element between two points in the same Cisco window, such as a module or physical object. Observe before and after.",
               {"window_id":WINDOW_ID,**{k:{"type":"integer","minimum":0} for k in ("from_x","from_y","to_x","to_y")}},["window_id","from_x","from_y","to_x","to_y"],False),
    definition("ui_scroll", "Scroll a Cisco area under point x,y; positive ticks scroll up, negative ticks scroll down.",
               {"window_id":WINDOW_ID,"x":{"type":"integer","minimum":0},"y":{"type":"integer","minimum":0},"ticks":{"type":"integer","minimum":-100,"maximum":100}},["window_id","x","y","ticks"],False),
]

# These engine operations rewrite a .pkt snapshot. They must never flatten a .pka.
PKT_ONLY = {"add_location", "rename_location", "remove_location", "arrange_devices",
            "move_to_location", "set_background", "draw", "remove_drawing", "connect_wireless"}


class Gateway:
    def __init__(self, settings, engine):
        self.settings = settings
        self.engine = engine
        self.files = LabFiles(Path(settings["downloads"]), Path(settings["workspace"]))
        self.native = {}
        self.lock = asyncio.Lock()
        self._ui = None

    async def raw(self, name, args):
        return await self.engine.call_tool(name, args, read_timeout_seconds=timedelta(seconds=150))

    async def data(self, name, args):
        result = await self.raw(name, args)
        if result.isError:
            raise RuntimeError("\n".join(c.text for c in result.content if isinstance(c, types.TextContent)))
        if result.structuredContent is not None:
            return result.structuredContent
        return json.loads(next(c.text for c in result.content if isinstance(c, types.TextContent)))

    async def current(self):
        result = await self.data("call_ipc", {"from":"appWindow", "steps":[
            {"method":"getActiveFile"}, {"method":"getSavedFilename"}]})
        return result.get("value") or ""

    def fresh_path(self, stem="sauvegarde", suffix=".pkt"):
        target = self.files.resolve_write(f"sauvegardes/{stem}-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}{suffix}")
        target.parent.mkdir(parents=True, exist_ok=True)
        return str(target)

    async def backup(self):
        current = await self.current()
        suffix = ".pka" if str(current).lower().endswith(".pka") else ".pkt"
        return await self.data("save_network", {"path":self.fresh_path(suffix=suffix)})

    async def call(self, name, args):
        async with self.lock:
            if name in {t.name for t in UI_TOOLS}:
                if self._ui is None:
                    from windows_ui import PacketTracerUI
                    self._ui = PacketTracerUI(self.settings["packet_tracer_home"])
                method = {"ui_windows":"list_windows", "ui_inspect":"inspect", "ui_screenshot":"screenshot",
                          "ui_click":"click", "ui_type_text":"type_text", "ui_press_keys":"press_keys", "ui_drag":"drag", "ui_scroll":"scroll"}[name]
                result = getattr(self._ui, method)(**args)
                if isinstance(result, bytes):
                    return types.CallToolResult(content=[types.ImageContent(type="image",data=base64.b64encode(result).decode("ascii"),mimeType="image/png")])
                return result
            if name == "tp_lister":
                return self.files.list_labs(**args)
            if name == "tp_lire":
                return self.files.read(**args)
            if name == "tp_preparer":
                return self.files.prepare(**args)
            if name == "tp_rapport":
                return self.files.save_report(**args)
            if name == "tp_vlsm":
                return plan_vlsm(**args)
            if name == "tp_demarrer":
                exe = Path(self.settings["packet_tracer_home"]) / "bin/PacketTracer.exe"
                if not exe.is_file():
                    raise ValueError(f"Packet Tracer not found: {exe}")
                subprocess.Popen([str(exe)], cwd=str(exe.parent), close_fds=True)
                return {"launched":True, "next":"status", "note":"Wait for the Cisco window; a Cisco sign-in may be required."}
            if name == "setup_exapp":
                # Cisco places meta.exe in bin on Windows, unlike pktctl's finder.
                from install import compile_registration
                pta = compile_registration(self.settings)
                return {"app_id":self.settings["app_id"],"pta":str(pta),
                        "meta_tool":str(Path(self.settings["packet_tracer_home"])/"bin/meta.exe"),
                        "steps":["In Cisco: Extensions > IPC > Configure Apps > Add, select this .pta file.",
                                 "Exit Cisco normally once to save, then reopen it and call status."]}
            if name == "tp_diagnostic":
                return {"connector":"1.0.0", "engine":"pktctl 0.2.2", "native_tools":len(self.native),
                        "downloads":str(self.files.downloads), "workspace":str(self.files.workspace),
                        "packet_tracer":await self.data("status",{}),
                        "limits":["Some windows do not have a Cisco API.", "Scores for protected activities may require the author password.",
                                  "Operations that rewrite a .pkt are restricted to .pkt files.", "call_ipc supports advanced operations; stay within the scope of the lab."]}
            if name not in self.native:
                raise ValueError(f"Unknown tool: {name}")
            args = dict(args)
            if name in {"open_network", "new_network"}:
                if name == "open_network":
                    source = self.files.resolve_read(args["path"])
                    if not source.is_relative_to(self.files.workspace):
                        args["path"] = self.files.prepare(str(source))["working_file"]
                # Save even an unsaved network before pktctl clears it.
                args["save_current_to"] = self.fresh_path(suffix=".pka" if str(await self.current()).lower().endswith(".pka") else ".pkt")
            elif name == "save_network":
                target = args.get("path") or await self.current()
                if not target:
                    target = self.fresh_path(stem="reseau")
                target = self.files.resolve_write(target)
                if target.suffix.lower() not in {".pka", ".pkt"}:
                    raise ValueError("The saved file must end in .pkt or .pka.")
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    import shutil
                    shutil.copy2(target, self.fresh_path(stem=target.stem, suffix=target.suffix))
                args["path"] = str(target)
            elif name in PKT_ONLY and str(await self.current()).lower().endswith(".pka"):
                raise ValueError("This operation rewrites a .pkt and is not validated for .pka activities. Use a separate .pkt for this operation.")
            elif name not in {"status", "describe_ipc", "setup_exapp", "screenshot", "watch_events"}:
                spec = self.native[name]
                if not (spec.annotations and spec.annotations.readOnlyHint):
                    current = await self.current()
                    if current and not Path(current).resolve().is_relative_to(self.files.workspace):
                        # The file may have been opened manually in the Cisco GUI.
                        await self.backup()
            return await self.raw(name, args)


async def main():
    settings_path = Path(os.environ.get("PACKETTRACER_MCP_SETTINGS", ROOT / "settings.json"))
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    env = dict(os.environ, PKTCTL_APP_ID=settings["app_id"], PKTCTL_SECRET=settings["secret"],
               PKTCTL_CALL_TIMEOUT_SECS="30", PKTCTL_PT_HOME=settings["packet_tracer_home"],
               PKTCTL_SETUP_DIR=str(ROOT / "registration"))
    if settings.get("address"):
        env["PKTCTL_ADDR"] = settings["address"]
    async with AsyncExitStack() as stack:
        reader, writer = await stack.enter_async_context(stdio_client(StdioServerParameters(
            command=str(ROOT / "vendor/pktctl.exe"), env=env)))
        engine = await stack.enter_async_context(ClientSession(reader, writer))
        await engine.initialize()
        gateway = Gateway(settings, engine)
        gateway.native = {t.name:t for t in (await engine.list_tools()).tools}
        server = Server("packettracer", version="1.0.0", instructions=INSTRUCTIONS)

        @server.list_tools()
        async def list_tools():
            return list(gateway.native.values()) + LOCAL_TOOLS + UI_TOOLS

        @server.call_tool()
        async def call_tool(name, arguments):
            try:
                result = await gateway.call(name, arguments or {})
                if isinstance(result, types.CallToolResult):
                    return result
                return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))], structuredContent=result)
            except Exception as error:
                return types.CallToolResult(isError=True, content=[types.TextContent(type="text", text=str(error))])

        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
