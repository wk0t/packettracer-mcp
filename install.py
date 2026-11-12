"""Install the Windows Packet Tracer connector; preserve existing credentials.

Run through install.ps1, or with Python 3.12 and uv on PATH. Importing this
module performs no installation. All subprocess arguments are passed as lists.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import subprocess
import struct
import sys
import tempfile
import urllib.request
import uuid
from xml.sax.saxutils import escape
import zipfile

VERSION = "0.2.2"
ARCHIVE_NAME = "pktctl-0.2.2-x86_64-pc-windows-msvc.zip"
ARCHIVE_URL = f"https://github.com/TantiE100/pktctl/releases/download/v{VERSION}/{ARCHIVE_NAME}"
ARCHIVE_SHA256 = "d4914f50e33a0673c78225a591b4ab28884301713a3561abceb126461c0f9cb8"
SOURCE = Path(__file__).resolve().parent
HOME = Path.home()
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
EXPECTED_TOOLS = 87
SOURCE_FILES = ("server.py", "coursework.py", "windows_ui.py", "doctor.py", "SKILL.md", "README.md", "LICENSE", "THIRD_PARTY.md", "requirements.txt")
UV_INSTALL_URL = "https://docs.astral.sh/uv/getting-started/installation/"


def default_install_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else HOME / "AppData" / "Local"
    return (base / "PacketTracerMCP").resolve()


def run(arguments: list[str], *, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(arguments, check=True, text=True, encoding="utf-8", errors="replace",
                          capture_output=capture, **({} if capture else {"stdout": sys.stderr, "stderr": sys.stderr}),
                          creationflags=NO_WINDOW)


def progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def fingerprint(path: Path) -> str | None:
    if not path.exists():
        return None
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.read_bytes() == data:
        return
    temporary = path.with_name(path.name + ".install-" + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def find_command(name: str) -> Path:
    found = shutil.which(name)
    if found:
        return Path(found)
    candidate = HOME / ".local" / "bin" / (name + ".exe")
    if candidate.is_file():
        return candidate
    if name == "uv":
        raise RuntimeError(f"uv is required. Install it from {UV_INSTALL_URL}, reopen PowerShell, and rerun install.ps1.")
    raise RuntimeError(f"Required command not found: {name}")


def discover_packet_tracer(explicit: str | None, settings: dict) -> Path:
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    elif settings.get("packet_tracer_home"):
        candidates.append(Path(settings["packet_tracer_home"]))
    if not explicit:
        for folder in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
            if folder and Path(folder).is_dir():
                candidates.extend(sorted(Path(folder).glob("Cisco Packet Tracer*"),
                                         key=lambda path: tuple(int(part) for part in re.findall(r"\d+", path.name)),
                                         reverse=True))
    for candidate in candidates:
        if (candidate / "bin" / "PacketTracer.exe").is_file() and (candidate / "bin" / "meta.exe").is_file():
            return candidate.resolve()
    raise RuntimeError("Packet Tracer with bin/PacketTracer.exe and bin/meta.exe was not found. Use --packet-tracer-home PATH.")


def read_vendor_archive(archive: Path) -> dict[str, bytes]:
    if not archive.is_file():
        raise RuntimeError("The --archive path must be an existing pktctl ZIP file. Check the path and retry.")
    if fingerprint(archive) != ARCHIVE_SHA256:
        raise RuntimeError("The pktctl archive SHA-256 does not match the expected release. Installation stopped.")
    with zipfile.ZipFile(archive) as package:
        contents = {}
        for leaf in ("pktctl.exe", "LICENSE", "README.md", "CHANGELOG.md"):
            members = [item for item in package.infolist() if item.filename.endswith("/" + leaf) and not item.is_dir()]
            if len(members) != 1 or members[0].file_size > 64 * 1024 * 1024:
                raise RuntimeError(f"Unexpected archive contents: {leaf}")
            contents[leaf] = package.read(members[0])
    return contents


def install_vendor(archive: Path, install_root: Path) -> None:
    contents = read_vendor_archive(archive)
    vendor = install_root / "vendor"
    # Check the whole archive before changing an existing vendor installation.
    for leaf, data in contents.items():
        atomic_write(vendor / leaf, data)
    result = run([str(vendor / "pktctl.exe"), "--version"], capture=True)
    if result.stdout.strip() != f"pktctl {VERSION}":
        raise RuntimeError("The installed engine did not report the expected version.")


def private_file(path: Path) -> None:
    account = os.environ.get("USERNAME")
    domain = os.environ.get("USERDOMAIN")
    if not account:
        raise RuntimeError("Cannot determine the Windows account needed to protect the credentials file.")
    identity = f"{domain}\\{account}" if domain else account
    # Credentials belong to the current user and SYSTEM; no broad inherited ACL.
    run(["icacls", str(path), "/inheritance:r", "/grant:r", f"{identity}:(F)", "*S-1-5-18:(F)"], capture=True)


def save_settings(settings_path: Path, old_bytes: bytes | None, settings: dict) -> None:
    payload = (json.dumps(settings, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if old_bytes is None:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        with settings_path.open("xb") as stream:
            stream.write(payload)
        private_file(settings_path)
    else:
        if settings_path.read_bytes() != old_bytes:
            raise RuntimeError("settings.json changed during installation; no update was applied.")
        if json.loads(old_bytes.decode("utf-8-sig")) != settings:
            atomic_write(settings_path, payload)
            private_file(settings_path)


def compile_registration(settings: dict, install_root: Path | None = None) -> Path:
    for key in ("app_id", "secret"):
        value = settings.get(key)
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", value):
            raise RuntimeError(f"The credentials field {key} has an unsupported format.")
    privileges = ("GET_NETWORK_INFO", "CHANGE_NETWORK_INFO", "SIMULATION_MODE", "MISC_GUI", "FILE", "CHANGE_PREFERENCES", "CHANGE_GUI", "ACTIVITY_WIZARD", "MULTIUSER", "IPC", "APPLICATION")
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>', '<!DOCTYPE PT_APP_META>', '<PT_APP_META>',
        '<PT_VERSION>9.0.0</PT_VERSION>', '<IPC_VERSION>1.0</IPC_VERSION>',
        '<NAME>Packet Tracer MCP</NAME>', '<VERSION>1.0</VERSION>',
        '<ID>' + escape(settings["app_id"]) + '</ID>',
        '<DESCRIPTION>Local MCP connector for Cisco Packet Tracer.</DESCRIPTION>',
        '<AUTHOR>Packet Tracer MCP</AUTHOR>', '<CONTACT>local</CONTACT>',
        '<EXECUTABLE_PATH>pktctl</EXECUTABLE_PATH>', '<KEY>' + escape(settings["secret"]) + '</KEY>',
        '<SECURITY_SETTINGS>', *('<PRIVILEGE>' + p + '</PRIVILEGE>' for p in privileges),
        '</SECURITY_SETTINGS>', '<LOADING>ON_DEMAND</LOADING>', '<SAVING>NEVER</SAVING>',
        '<INSTANCES>1</INSTANCES>', '</PT_APP_META>',
    ]
    registration = (install_root if install_root is not None else SOURCE) / "registration"
    registration.mkdir(parents=True, exist_ok=True)
    destination = registration / "packettracer-mcp.pta"
    # The temporary XML contains a secret; it is private and removed in all cases.
    xml = registration / (".meta-" + uuid.uuid4().hex + ".xml")
    staged = registration / (".meta-" + uuid.uuid4().hex + ".pta")
    try:
        with xml.open("xb") as stream:
            stream.write(("\n".join(lines) + "\n").encode("utf-8"))
        private_file(xml)
        run([str(Path(settings["packet_tracer_home"]) / "bin" / "meta.exe"), str(staged), str(xml)], capture=True)
        if not staged.is_file() or staged.stat().st_size < 100:
            raise RuntimeError("The Cisco tool did not produce a valid .pta file.")
        # Keep a registered, unchanged pta stable across routine reinstallation.
        atomic_write(destination, staged.read_bytes())
        private_file(destination)
    finally:
        xml.unlink(missing_ok=True)
        staged.unlink(missing_ok=True)
    return destination


def write_mcp_config(python: Path, install_root: Path) -> Path:
    fragment = {"mcpServers": {"packettracer": {
        "command": str(python.resolve()),
        "args": [str((install_root / "server.py").resolve()), "--settings", str((install_root / "settings.json").resolve())],
    }}}
    destination = install_root / "mcp-config.json"
    atomic_write(destination, (json.dumps(fragment, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return destination


def validate_directory(path: Path, label: str) -> None:
    """Check an existing path or its nearest existing parent without creating it."""
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    if not candidate.is_dir():
        raise RuntimeError(f"{label} must be a folder, with an existing parent folder. Choose another path and retry.")


def validate_settings(settings: dict, *, existing: bool) -> None:
    if not isinstance(settings, dict):
        raise RuntimeError("settings.json must contain a JSON object. Restore a valid settings file and retry; existing credentials were left unchanged.")
    for field in ("app_id", "secret") if existing else ("app_id",):
        value = settings.get(field)
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", value):
            raise RuntimeError(f"Invalid settings field: {field}. Restore its existing value in settings.json and retry; credentials were left unchanged.")
    for field in ("downloads", "workspace"):
        value = settings.get(field)
        if not isinstance(value, str) or not value.strip() or "\0" in value:
            raise RuntimeError(f"Invalid settings field: {field}. Set it to a folder path in settings.json and retry.")
        validate_directory(Path(value).resolve(), f"The settings field {field}")
    downloads, workspace = (Path(settings[field]).resolve() for field in ("downloads", "workspace"))
    if downloads.is_relative_to(workspace) or workspace.is_relative_to(downloads):
        raise RuntimeError("The downloads and workspace folders in settings.json must be separate, with neither inside the other. Choose a separate workspace and retry.")
    if "packet_tracer_home" in settings and (
        not isinstance(settings["packet_tracer_home"], str) or not settings["packet_tracer_home"].strip()
        or "\0" in settings["packet_tracer_home"]
    ):
        raise RuntimeError("Invalid settings field: packet_tracer_home. Set it to the Cisco Packet Tracer folder and retry.")
    if "address" in settings:
        address = settings["address"]
        if not isinstance(address, str) or not re.fullmatch(r"(?:\[[^\]\s]+\]|[^:\s]+):[0-9]+", address):
            raise RuntimeError("Invalid settings field: address. Use HOST:PORT, such as 127.0.0.1:39000, and retry.")
        if not 1 <= int(address.rsplit(":", 1)[1]) <= 65535:
            raise RuntimeError("Invalid settings field: address. Use a port between 1 and 65535 and retry.")


def preflight(args: argparse.Namespace) -> dict:
    """Read prerequisites and user inputs before any installation side effects."""
    architecture = os.environ.get("PROCESSOR_ARCHITEW6432", platform.machine()).lower()
    if os.name != "nt" or architecture not in ("amd64", "x86_64") or struct.calcsize("P") != 8:
        raise RuntimeError("This installer requires Windows x64 and 64-bit Python. Use a Windows x64 computer with 64-bit Python 3.12 or newer.")
    if sys.version_info < (3, 12):
        raise RuntimeError("Python 3.12 or newer is required. Install 64-bit Python from https://www.python.org/downloads/windows/ and rerun install.ps1.")
    for filename in SOURCE_FILES:
        if not (SOURCE / filename).is_file():
            raise RuntimeError(f"Missing source file: {filename}. Extract the complete project archive or restore the checkout and retry.")
    install_root = args.install_dir.expanduser().resolve() if args.install_dir is not None else default_install_root()
    validate_directory(install_root, "The installation path")
    for relative in (".venv/Scripts", "vendor", "registration", "skills/packettracer-tp", "docs"):
        validate_directory(install_root / relative, f"The installation subfolder {relative}")
    destinations = (*SOURCE_FILES, "install.py", "install.ps1", "mcp-config.json", ".venv/Scripts/python.exe")
    for relative in destinations:
        destination = install_root / relative
        if destination.exists() and not destination.is_file():
            raise RuntimeError(f"The installation destination {relative} must be a file. Choose another installation folder or move the conflicting folder and retry.")
    settings_path = install_root / "settings.json"
    if settings_path.exists() and not settings_path.is_file():
        raise RuntimeError("settings.json must be a file. Choose another installation folder or restore the settings file and retry.")
    old_bytes = settings_path.read_bytes() if settings_path.is_file() else None
    if old_bytes is not None:
        try:
            settings = json.loads(old_bytes.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise RuntimeError("settings.json is not valid UTF-8 JSON. Restore a valid settings file and retry; existing credentials were left unchanged.") from None
    else:
        settings = {
            "app_id": "local.packettracer.mcp", "address": "127.0.0.1:39000",
            "downloads": str(HOME / "Downloads"), "workspace": str(HOME / "Documents" / "PacketTracer-TP"),
        }
    validate_settings(settings, existing=old_bytes is not None)
    packet_tracer_home = discover_packet_tracer(args.packet_tracer_home, settings)
    if args.packet_tracer_home is not None or not settings.get("packet_tracer_home"):
        settings["packet_tracer_home"] = str(packet_tracer_home)
    archive = args.archive.expanduser().resolve() if args.archive is not None else None
    if archive is not None:
        try:
            read_vendor_archive(archive)
        except zipfile.BadZipFile:
            raise RuntimeError("The --archive file is not a valid pktctl ZIP archive. Download the expected archive again and retry.") from None
    uv = find_command("uv")
    return {"install_root": install_root, "settings_path": settings_path, "old_bytes": old_bytes,
            "settings": settings, "packet_tracer_home": packet_tracer_home, "archive": archive, "uv": uv}


def doctor_command(install_root: Path) -> str:
    values = (install_root / ".venv" / "Scripts" / "python.exe", install_root / "doctor.py", "--settings", install_root / "settings.json")
    return "& " + " ".join("'" + str(value).replace("'", "''") + "'" for value in values)


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the local Packet Tracer MCP connector for any compatible MCP client.")
    parser.add_argument("--archive", type=Path, help="Offline Windows pktctl archive (SHA-256 verified).")
    parser.add_argument("--install-dir", type=Path, help="Installation folder (default: %%LOCALAPPDATA%%/PacketTracerMCP).")
    parser.add_argument("--packet-tracer-home", help="Cisco Packet Tracer folder containing bin/meta.exe.")
    parser.add_argument("--check", action="store_true", help="Check local prerequisites and inputs without downloads, installation, or changes.")
    args = parser.parse_args()
    progress("[1/5] Checking prerequisites and installation inputs...")
    plan = preflight(args)
    install_root, settings_path = plan["install_root"], plan["settings_path"]
    old_bytes, settings, uv = plan["old_bytes"], plan["settings"], plan["uv"]
    if args.check:
        progress("Preflight passed. No files were changed; downloads and live IPC were not tested.")
        print(json.dumps({"check": "passed", "install_dir": str(install_root), "python": sys.executable,
                          "uv": str(uv), "packet_tracer_home": str(plan["packet_tracer_home"]),
                          "archive": str(plan["archive"]) if plan["archive"] is not None else "download during installation",
                          "existing_settings": old_bytes is not None, "expected_tools": EXPECTED_TOOLS,
                          "doctor_command": doctor_command(install_root),
                          "next": "Run install.ps1 with the same options and without -Check to install."}, ensure_ascii=False, indent=2))
        return 0
    if old_bytes is None:
        settings["secret"] = secrets.token_hex(32)
    python = install_root / ".venv" / "Scripts" / "python.exe"
    with ExitStack() as temporary:
        progress("[2/5] Preparing the verified pktctl engine...")
        archive = plan["archive"]
        if archive is None:
            folder = temporary.enter_context(tempfile.TemporaryDirectory(prefix="packettracer-install-"))
            archive = Path(folder) / ARCHIVE_NAME
            request = urllib.request.Request(ARCHIVE_URL, headers={"User-Agent": "PacketTracer-MCP-Installer/1.0"})
            try:
                with urllib.request.urlopen(request, timeout=60) as response, archive.open("wb") as output:
                    shutil.copyfileobj(response, output)
            except OSError:
                raise RuntimeError("The pktctl download failed. Check your network, or download the release ZIP separately and rerun with --archive PATH.") from None
            read_vendor_archive(archive)
        progress("[3/5] Preparing the Python environment and dependencies...")
        install_root.mkdir(parents=True, exist_ok=True)
        if not python.is_file():
            run([str(uv), "venv", "--no-python-downloads", "--python", sys.executable, str(install_root / ".venv")])
        run([str(uv), "pip", "install", "--python", str(python), "--requirements", str(SOURCE / "requirements.txt")])
        progress("[4/5] Installing connector files and the engine...")
        for filename in (*SOURCE_FILES, "install.py", "install.ps1"):
            if (SOURCE / filename).is_file():
                atomic_write(install_root / filename, (SOURCE / filename).read_bytes())
        for source in sorted((SOURCE / "docs").glob("*")):
            if source.is_file() and source.suffix in (".md", ".json"):
                atomic_write(install_root / "docs" / source.name, source.read_bytes())
        skill = install_root / "skills" / "packettracer-tp" / "SKILL.md"
        atomic_write(skill, (SOURCE / "SKILL.md").read_bytes())
        install_vendor(archive, install_root)
    progress("[5/5] Preserving credentials and preparing Cisco registration...")
    save_settings(settings_path, old_bytes, settings)
    pta = compile_registration(settings, install_root)
    config = write_mcp_config(python, install_root)
    print(json.dumps({"installed": str(install_root), "engine": f"pktctl {VERSION}",
                      "mcp_config": str(config), "skill": str(skill),
                      "registration": str(pta), "workspace": settings["workspace"],
                      "expected_tools": EXPECTED_TOOLS, "doctor_command": doctor_command(install_root),
                      "next": "Import mcp-config.json into your MCP client. In Packet Tracer, add the .pta file in Extensions > IPC > Configure Apps if needed, enable IPC, and exit normally once to save it. Reopen Packet Tracer, then run doctor_command; a healthy connection exposes 87 tools."}, ensure_ascii=False, indent=2))
    progress("Installation complete. Follow the next steps in the JSON result.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError, zipfile.BadZipFile) as error:
        # Do not echo child output or credential values on failure.
        if isinstance(error, subprocess.CalledProcessError):
            print(f"An installation command failed (exit code {error.returncode}). No credentials are displayed.", file=sys.stderr)
        else:
            print(f"Installation stopped: {error}", file=sys.stderr)
        raise SystemExit(1)
