"""Read-only installation and MCP connection diagnostics."""
from __future__ import annotations

import argparse
import asyncio
from importlib import metadata
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
from datetime import timedelta

EXPECTED_TOOLS = 87
EXPECTED_ENGINE = "pktctl 0.2.2"


def _add(report, name, status, message, action=None):
    item = {"name":name,"status":status,"message":message}
    if action:
        item["action"] = action
    report["checks"].append(item)


def _finish(report):
    states = {check["status"] for check in report["checks"]}
    report["status"] = "error" if "fail" in states else "attention" if "attention" in states else "ready"
    return report,{"ready":0,"attention":2,"error":1}[report["status"]]


def _default_settings():
    adjacent = Path(__file__).resolve().parent / "settings.json"
    if adjacent.is_file():
        return adjacent
    base = Path(os.environ.get("LOCALAPPDATA",Path.home()/"AppData/Local"))
    return base/"PacketTracerMCP/settings.json"


def read_client_entry(root, settings_path):
    """Validate the generated launch command, including its settings target."""
    config = json.loads((root/"mcp-config.json").read_text(encoding="utf-8-sig"))
    entry = config["mcpServers"]["packettracer"]
    command, arguments = entry["command"], entry["args"]
    python = root/".venv/Scripts/python.exe"
    if not isinstance(command,str) or not python.is_file() or Path(command).resolve() != python.resolve():
        raise ValueError("incorrect interpreter")
    if not isinstance(arguments,list) or not all(isinstance(value,str) for value in arguments) or len(arguments) not in (3,5):
        raise ValueError("invalid arguments")
    if Path(arguments[0]).resolve() != (root/"server.py").resolve() or not (root/"server.py").is_file():
        raise ValueError("incorrect server")
    options = dict(zip(arguments[1::2],arguments[2::2]))
    if len(options) != (len(arguments)-1)//2 or set(options)-{"--settings","--runtime-dir"}:
        raise ValueError("unsupported launch options")
    if "--settings" not in options or Path(options["--settings"]).resolve() != settings_path:
        raise ValueError("incorrect settings target")
    if "--runtime-dir" in options:
        if Path(options["--runtime-dir"]).resolve() != root:
            raise ValueError("incorrect runtime directory")
    elif settings_path.parent != root:
        raise ValueError("runtime directory required")
    return entry


def inspect_install(settings_file=None, runtime_dir=None):
    """Inspect local files and dependency versions without changing the installation."""
    settings_path = Path(settings_file or os.environ.get("PACKETTRACER_MCP_SETTINGS") or _default_settings()).expanduser().resolve()
    root = Path(runtime_dir).expanduser().resolve() if runtime_dir else settings_path.parent
    report = {"status":"ready","mode":"offline","expected_tools":EXPECTED_TOOLS,"checks":[],"paths":{
        "installation":str(root),"settings":str(settings_path),
        "registration":str(root/"registration/packettracer-mcp.pta"),"mcp_config":str(root/"mcp-config.json")}}
    if sys.platform == "win32" and struct.calcsize("P") == 8 and sys.version_info >= (3,12):
        _add(report,"python","pass","Windows 64-bit Python 3.12+ is available.")
    else:
        _add(report,"python","fail","This connector requires Windows 64-bit Python 3.12+.","Run this command using the installation's .venv\\Scripts\\python.exe.")
    settings = None
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8-sig"))
        if not isinstance(settings,dict):
            raise ValueError("object required")
        for field in ("app_id","secret","downloads","workspace","packet_tracer_home"):
            if not isinstance(settings.get(field),str) or not settings[field].strip():
                raise ValueError("missing field")
        for field in ("app_id","secret"):
            if not re.fullmatch(r"[A-Za-z0-9._-]+",settings[field]):
                raise ValueError("invalid credentials format")
        downloads,workspace = Path(settings["downloads"]).resolve(),Path(settings["workspace"]).resolve()
        if downloads.is_relative_to(workspace) or workspace.is_relative_to(downloads):
            raise ValueError("overlapping roots")
        if "address" in settings:
            address = settings["address"]
            if not isinstance(address,str) or not re.fullmatch(r"(?:\[[^\]\s]+\]|[^:\s]+):[0-9]+",address):
                raise ValueError("invalid address")
            if not 1 <= int(address.rsplit(":",1)[1]) <= 65535:
                raise ValueError("invalid port")
        _add(report,"settings","pass","Settings are valid and source/output folders are separate.")
    except (OSError,ValueError,TypeError):
        settings = None
        _add(report,"settings","fail","Settings are missing, invalid, or use overlapping source/output folders.","Check settings.json: use separate downloads/workspace folders and a HOST:PORT address, or rerun install.ps1.")
    missing = [leaf for leaf in ("server.py","coursework.py","windows_ui.py","install.py","requirements.txt") if not (root/leaf).is_file()]
    if missing:
        _add(report,"files","fail","Required installation files are missing: "+", ".join(missing),"Rerun install.ps1 for this installation directory.")
    else:
        _add(report,"files","pass","Required server files are present.")
    dependency_issues = []
    try:
        requirements = (root/"requirements.txt").read_text(encoding="utf-8-sig")
        pins = []
        for line in requirements.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s;]+)",line)
            if not match:
                raise ValueError("unsupported requirement")
            pins.append(match.groups())
        if not pins:
            raise ValueError("empty requirements")
        for package,expected in pins:
            try:
                if metadata.version(package) != expected:
                    dependency_issues.append(package+" (version mismatch)")
            except metadata.PackageNotFoundError:
                dependency_issues.append(package+" (missing)")
        if dependency_issues:
            raise ValueError("dependency mismatch")
        _add(report,"dependencies","pass",f"All {len(pins)} pinned Python dependencies are installed.")
    except (OSError,ValueError):
        message = "Missing or incompatible Python dependencies"
        if dependency_issues:
            message += ": "+", ".join(dependency_issues)
        _add(report,"dependencies","fail",message+".","Use the installed Python interpreter, or rerun install.ps1 to repair the environment.")
    engine = root/"vendor/pktctl.exe"
    try:
        if not engine.is_file():
            raise OSError("missing engine")
        version = subprocess.run([str(engine),"--version"],capture_output=True,text=True,
            encoding="utf-8",errors="replace",timeout=10,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        if version.returncode != 0 or version.stdout.strip() != EXPECTED_ENGINE:
            raise ValueError("unexpected engine version")
        _add(report,"engine","pass",EXPECTED_ENGINE+" is available.")
    except (OSError,ValueError,subprocess.SubprocessError):
        _add(report,"engine","fail","The native engine is missing or does not report the expected version.","Rerun install.ps1; use -Archive with the verified Windows engine archive if needed.")
    if settings is not None:
        executable = Path(settings["packet_tracer_home"])/"bin/PacketTracer.exe"
        if executable.is_file():
            _add(report,"cisco_installation","pass","The configured Packet Tracer executable exists.")
        else:
            _add(report,"cisco_installation","fail","The configured Packet Tracer executable was not found.","Rerun install.ps1 -PacketTracerHome PATH with the Cisco installation directory.")
    if Path(report["paths"]["registration"]).is_file():
        _add(report,"registration_file","pass","The Cisco registration file is present; registration inside Cisco is checked in live mode.")
    else:
        _add(report,"registration_file","fail","The generated Cisco registration file is missing.","Rerun install.ps1 to regenerate registration/packettracer-mcp.pta.")
    try:
        read_client_entry(root,settings_path)
        _add(report,"client_fragment","pass","The generated MCP fragment targets this installation and its settings.")
    except (OSError,ValueError,KeyError,TypeError):
        _add(report,"client_fragment","fail","The generated MCP connection fragment is missing or invalid.","Rerun install.ps1 to regenerate mcp-config.json, then merge its entry into your client.")
    return _finish(report)[0]


async def probe_client(settings_path, runtime_root, timeout):
    """Initialize MCP, discover tools and read simulator status; never change a lab."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    entry = read_client_entry(runtime_root,settings_path)
    parameters = StdioServerParameters(command=entry["command"],args=entry["args"],cwd=str(runtime_root))
    async with asyncio.timeout(timeout):
        with open(os.devnull,"w") as sink:
            async with stdio_client(parameters,errlog=sink) as (read,write):
                async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=timeout)) as client:
                    initialized = await client.initialize()
                    tools = (await client.list_tools()).tools
                    response = await client.call_tool("status",{})
                    if response.isError:
                        raise RuntimeError("Status tool failed")
                    status = response.structuredContent
                    if status is None:
                        status = json.loads(next(item.text for item in response.content if item.type=="text"))
                    if not isinstance(status,dict) or type(status.get("connected")) is not bool:
                        raise ValueError("Invalid status response")
                    return {"tools":len(tools),"packet_tracer":status,"server_version":initialized.serverInfo.version}


async def diagnose(settings_file=None, runtime_dir=None, *, offline=False, timeout=30):
    report = inspect_install(settings_file,runtime_dir)
    report["mode"] = "offline" if offline else "live"
    if report["status"] == "error" or offline:
        return _finish(report)
    try:
        result = await probe_client(Path(report["paths"]["settings"]),Path(report["paths"]["installation"]),timeout)
        report["tools"] = result["tools"]
        if result["tools"] != EXPECTED_TOOLS:
            _add(report,"mcp","fail",f"MCP responded with {result['tools']} tools; expected {EXPECTED_TOOLS}.","Rerun install.ps1, then refresh your client's tool discovery.")
        else:
            _add(report,"mcp","pass",f"MCP initialized and advertised {EXPECTED_TOOLS} tools.")
        state = result["packet_tracer"]
        report["packet_tracer"] = {"connected":state.get("connected") is True}
        if state.get("pt_version"):
            report["packet_tracer"]["version"] = str(state["pt_version"])
        if state.get("connected") is True:
            _add(report,"cisco_connection","pass","The live Packet Tracer connection is ready.")
        else:
            _add(report,"cisco_connection","attention","MCP is ready, but Packet Tracer is not connected.",
                "Open Cisco, then Extensions > IPC > Configure Apps to add the .pta. Enable local IPC listening, exit Cisco normally once, reopen it and retry.")
    except Exception as error:
        _add(report,"mcp","fail",f"The MCP connection check failed ({type(error).__name__}).",
            "Verify the installed Python/server paths and rerun install.ps1. Retry with a longer --timeout if startup is slow.")
    return _finish(report)


def render_report(report, *, as_json=False):
    if as_json:
        return json.dumps(report,ensure_ascii=False,indent=2)
    lines = ["Packet Tracer MCP - "+report["status"].upper()+" ("+report["mode"]+")"]
    labels = {"pass":"OK","attention":"NEXT","fail":"FIX"}
    for check in report["checks"]:
        lines.append(f"[{labels[check['status']]}] {check['message']}")
        if check.get("action"):
            lines.append("      "+check["action"])
    lines.append("Config: "+report["paths"]["mcp_config"])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Check an installed Packet Tracer MCP connector without changing lab files.")
    parser.add_argument("--settings",help="Settings JSON path; otherwise use the environment or default installation.")
    parser.add_argument("--runtime-dir",help="Installed server/engine directory; defaults to the settings directory.")
    parser.add_argument("--offline",action="store_true",help="Check local files, dependencies and engine version without starting an MCP session.")
    parser.add_argument("--json",action="store_true",help="Print a machine-readable diagnostic report.")
    parser.add_argument("--timeout",type=int,default=30,help="Live startup/status timeout in seconds (5-120; default 30).")
    args = parser.parse_args()
    if not 5 <= args.timeout <= 120:
        parser.error("--timeout must be between 5 and 120 seconds")
    report,code = asyncio.run(diagnose(args.settings,args.runtime_dir,offline=args.offline,timeout=args.timeout))
    print(render_report(report,as_json=args.json))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
