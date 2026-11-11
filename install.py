"""Install the Windows Packet Tracer connector; preserve existing credentials.

Run through install.ps1, or with Python 3.12 and uv on PATH. Importing this
module performs no installation. All subprocess arguments are passed as lists.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
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


def default_install_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else HOME / "AppData" / "Local"
    return (base / "PacketTracerMCP").resolve()


def run(arguments: list[str], *, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(arguments, check=True, text=True, encoding="utf-8", errors="replace",
                          capture_output=capture, creationflags=NO_WINDOW)


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


def install_vendor(archive: Path, install_root: Path) -> None:
    if fingerprint(archive) != ARCHIVE_SHA256:
        raise RuntimeError("The pktctl archive SHA-256 does not match the expected release. Installation stopped.")
    vendor = install_root / "vendor"
    with zipfile.ZipFile(archive) as package:
        contents = {}
        for leaf in ("pktctl.exe", "LICENSE", "README.md", "CHANGELOG.md"):
            members = [item for item in package.infolist() if item.filename.endswith("/" + leaf) and not item.is_dir()]
            if len(members) != 1 or members[0].file_size > 64 * 1024 * 1024:
                raise RuntimeError(f"Unexpected archive contents: {leaf}")
            contents[leaf] = package.read(members[0])
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the local Packet Tracer MCP connector for any compatible MCP client.")
    parser.add_argument("--archive", type=Path, help="Offline Windows pktctl archive (SHA-256 verified).")
    parser.add_argument("--install-dir", type=Path, help="Installation folder (default: %%LOCALAPPDATA%%/PacketTracerMCP).")
    parser.add_argument("--packet-tracer-home", help="Cisco Packet Tracer folder containing bin/meta.exe.")
    args = parser.parse_args()
    if os.name != "nt":
        raise RuntimeError("This installer supports Windows x64.")
    if sys.version_info < (3, 12):
        raise RuntimeError("Use Python 3.12 or install.ps1.")
    for filename in ("server.py", "coursework.py", "windows_ui.py", "SKILL.md", "README.md", "THIRD_PARTY.md", "requirements.txt"):
        if not (SOURCE / filename).is_file():
            raise RuntimeError(f"Missing source file: {filename}")
    install_root = args.install_dir.expanduser().resolve() if args.install_dir is not None else default_install_root()
    uv = find_command("uv")
    install_root.mkdir(parents=True, exist_ok=True)
    settings_path = install_root / "settings.json"
    old_bytes = settings_path.read_bytes() if settings_path.is_file() else None
    settings = json.loads(old_bytes.decode("utf-8-sig")) if old_bytes is not None else {
        "app_id": "local.packettracer.mcp", "secret": secrets.token_hex(32),
        "address": "127.0.0.1:39000", "downloads": str(HOME / "Downloads"),
        "workspace": str(HOME / "Documents" / "PacketTracer-TP"),
    }
    packet_tracer_home = discover_packet_tracer(args.packet_tracer_home, settings)
    if args.packet_tracer_home is not None or not settings.get("packet_tracer_home"):
        settings["packet_tracer_home"] = str(packet_tracer_home)
    python = install_root / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        run([str(uv), "venv", "--python", "3.12", str(install_root / ".venv")])
    run([str(uv), "pip", "install", "--python", str(python), "--requirements", str(SOURCE / "requirements.txt")])
    for filename in ("server.py", "coursework.py", "windows_ui.py", "SKILL.md", "README.md", "THIRD_PARTY.md", "requirements.txt", "install.py", "install.ps1"):
        if (SOURCE / filename).is_file():
            atomic_write(install_root / filename, (SOURCE / filename).read_bytes())
    skill = install_root / "skills" / "packettracer-tp" / "SKILL.md"
    atomic_write(skill, (SOURCE / "SKILL.md").read_bytes())
    with tempfile.TemporaryDirectory(prefix="packettracer-install-") as folder:
        archive = args.archive.resolve() if args.archive else Path(folder) / ARCHIVE_NAME
        if args.archive is None:
            request = urllib.request.Request(ARCHIVE_URL, headers={"User-Agent": "PacketTracer-MCP-Installer/1.0"})
            with urllib.request.urlopen(request, timeout=60) as response, archive.open("wb") as output:
                shutil.copyfileobj(response, output)
        install_vendor(archive, install_root)
    save_settings(settings_path, old_bytes, settings)
    pta = compile_registration(settings, install_root)
    config = write_mcp_config(python, install_root)
    print(json.dumps({"installed": str(install_root), "engine": f"pktctl {VERSION}",
                      "mcp_config": str(config), "skill": str(skill),
                      "registration": str(pta), "workspace": settings["workspace"],
                      "next": "Import the MCP configuration fragment into your client. If needed, add the .pta file in Extensions > IPC > Configure Apps and exit Packet Tracer normally once."}, ensure_ascii=False, indent=2))
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
