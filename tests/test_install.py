import importlib.util
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

spec = importlib.util.spec_from_file_location("packettracer_install", Path(__file__).resolve().parents[1] / "install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
private_file = installer.private_file
find_command_original = installer.find_command


def test_native_windows_output_with_oem_bytes_is_captured():
    result = installer.run([sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'install\\x82')"], capture=True)
    assert isinstance(result.stdout, str) and result.stdout.startswith("install")


@pytest.fixture
def isolated_install(tmp_path, monkeypatch):
    """Keep all installer operations inside pytest's temporary directory."""
    monkeypatch.setattr(installer, "HOME", tmp_path / "home")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))

    def forbidden(*args, **kwargs):
        pytest.fail("Unexpected external command during an offline installer test")

    monkeypatch.setattr(installer, "run", forbidden)
    monkeypatch.setattr(installer, "find_command", forbidden)
    monkeypatch.setattr(installer, "private_file", lambda path: None)
    return tmp_path


def make_archive(tmp_path, monkeypatch, names=None):
    archive = tmp_path / "engine.zip"
    if names is None:
        names = ["pktctl.exe", "LICENSE", "README.md", "CHANGELOG.md"]
    with zipfile.ZipFile(archive, "w") as package:
        for index, name in enumerate(names):
            package.writestr(f"release-{index}/{name}", name.encode("ascii"))
    monkeypatch.setattr(installer, "ARCHIVE_SHA256", hashlib.sha256(archive.read_bytes()).hexdigest())
    return archive


def packet_tracer_folder(path):
    (path / "bin").mkdir(parents=True)
    for filename in ("PacketTracer.exe", "meta.exe"):
        (path / "bin" / filename).write_bytes(b"test placeholder")
    return path


def test_fingerprint_handles_missing_and_binary_files(isolated_install):
    path = isolated_install / "binary.dat"
    assert installer.fingerprint(path) is None
    payload = b"\x00\xff\x82\r\n"
    path.write_bytes(payload)
    assert installer.fingerprint(path) == hashlib.sha256(payload).hexdigest()


def test_archive_hash_mismatch_does_not_write_vendor_files(isolated_install):
    archive = isolated_install / "untrusted.zip"
    archive.write_bytes(b"untrusted download")
    with pytest.raises(RuntimeError, match="SHA-256"):
        installer.install_vendor(archive, isolated_install / "extension")
    assert not (isolated_install / "extension").exists()


@pytest.mark.parametrize("names", [
    ["pktctl.exe", "LICENSE", "README.md"],
    ["pktctl.exe", "LICENSE", "README.md", "CHANGELOG.md", "CHANGELOG.md"],
])
def test_invalid_archive_preserves_existing_vendor_files(isolated_install, monkeypatch, names):
    archive = make_archive(isolated_install, monkeypatch, names)
    existing = (isolated_install / "extension") / "vendor" / "pktctl.exe"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"previous engine")
    with pytest.raises(RuntimeError, match="Unexpected archive contents"):
        installer.install_vendor(archive, isolated_install / "extension")
    assert {path.name: path.read_bytes() for path in existing.parent.iterdir()} == {"pktctl.exe": b"previous engine"}


def test_corrupt_zip_is_rejected_before_writes(isolated_install, monkeypatch):
    archive = isolated_install / "corrupt.zip"
    archive.write_bytes(b"not a ZIP file")
    monkeypatch.setattr(installer, "ARCHIVE_SHA256", installer.fingerprint(archive))
    with pytest.raises(zipfile.BadZipFile):
        installer.install_vendor(archive, isolated_install / "extension")
    assert not (isolated_install / "extension").exists()


def test_verified_archive_checks_exact_engine_version(isolated_install, monkeypatch):
    archive = make_archive(isolated_install, monkeypatch)
    calls = []

    def version(arguments, *, capture=False):
        calls.append((arguments, capture))
        return subprocess.CompletedProcess(arguments, 0, stdout=f"pktctl {installer.VERSION}\n")

    monkeypatch.setattr(installer, "run", version)
    installer.install_vendor(archive, isolated_install / "extension")
    assert calls == [([str((isolated_install / "extension") / "vendor" / "pktctl.exe"), "--version"], True)]
    for name in ("pktctl.exe", "LICENSE", "README.md", "CHANGELOG.md"):
        assert ((isolated_install / "extension") / "vendor" / name).read_bytes() == name.encode("ascii")


@pytest.mark.parametrize("reported", ["pktctl 0.2.1", "pktctl 0.2.2\nextra output"])
def test_wrong_engine_version_is_rejected(isolated_install, monkeypatch, reported):
    archive = make_archive(isolated_install, monkeypatch)
    monkeypatch.setattr(installer, "run", lambda args, **kwargs: subprocess.CompletedProcess(args, 0, stdout=reported))
    with pytest.raises(RuntimeError, match="expected version"):
        installer.install_vendor(archive, isolated_install / "extension")


def test_explicit_packet_tracer_path_takes_priority(isolated_install, monkeypatch):
    explicit = packet_tracer_folder(isolated_install / "explicit")
    previous = packet_tracer_folder(isolated_install / "previous")
    monkeypatch.setenv("ProgramFiles", str(isolated_install))
    assert installer.discover_packet_tracer(str(explicit), {"packet_tracer_home": str(previous)}) == explicit.resolve()


def test_invalid_explicit_packet_tracer_path_does_not_fall_back(isolated_install):
    previous = packet_tracer_folder(isolated_install / "previous")
    invalid = isolated_install / "invalid"
    (invalid / "bin").mkdir(parents=True)
    (invalid / "bin" / "PacketTracer.exe").write_bytes(b"missing meta.exe")
    with pytest.raises(RuntimeError, match="--packet-tracer-home"):
        installer.discover_packet_tracer(str(invalid), {"packet_tracer_home": str(previous)})


def test_discovery_preserves_working_saved_path(isolated_install, monkeypatch):
    saved = packet_tracer_folder(isolated_install / "saved")
    packet_tracer_folder(isolated_install / "Cisco Packet Tracer 10.0")
    monkeypatch.setenv("ProgramFiles", str(isolated_install))
    assert installer.discover_packet_tracer(None, {"packet_tracer_home": str(saved)}) == saved.resolve()


def test_discovery_compares_numeric_versions(isolated_install, monkeypatch):
    packet_tracer_folder(isolated_install / "Cisco Packet Tracer 9.0")
    latest = packet_tracer_folder(isolated_install / "Cisco Packet Tracer 10.0")
    packet_tracer_folder(isolated_install / "Cisco Packet Tracer 8.2")
    monkeypatch.setenv("ProgramFiles", str(isolated_install))
    monkeypatch.delenv("ProgramFiles(x86)", raising=False)
    assert installer.discover_packet_tracer(None, {}) == latest.resolve()


def test_unchanged_settings_preserve_credentials_and_bytes(isolated_install, monkeypatch):
    path = (isolated_install / "extension") / "settings.json"
    settings = {"app_id": "org.previous.connector", "secret": "existing-secret"}
    protected = []
    monkeypatch.setattr(installer, "private_file", protected.append)
    installer.save_settings(path, None, settings)
    initial = path.read_bytes()
    installer.save_settings(path, initial, dict(settings))
    assert path.read_bytes() == initial
    assert protected == [path]


@pytest.mark.parametrize("requested_change", [False, True])
def test_concurrent_settings_edit_is_preserved(isolated_install, requested_change):
    path = isolated_install / "settings.json"
    original = b'{"secret":"original"}\n'
    concurrent = b'{"secret":"concurrent"}\n'
    path.write_bytes(concurrent)
    settings = {"secret": "replacement" if requested_change else "original"}
    with pytest.raises(RuntimeError, match="settings.json changed"):
        installer.save_settings(path, original, settings)
    assert path.read_bytes() == concurrent


def test_registration_metadata_and_temporary_secret_cleanup(isolated_install, monkeypatch):
    captured = []
    settings = {
        "app_id": "org.previous.connector", "secret": "existing-secret",
        "packet_tracer_home": str(isolated_install / "packet tracer"),
    }

    def compile_meta(arguments, *, capture=False):
        captured.append((arguments, Path(arguments[2]).read_text(encoding="utf-8")))
        Path(arguments[1]).write_bytes(b"compiled registration" * 10)

    monkeypatch.setattr(installer, "run", compile_meta)
    destination = installer.compile_registration(settings, isolated_install / "extension")
    assert destination.name == "packettracer-mcp.pta"
    arguments, metadata = captured[0]
    assert arguments[0] == str(Path(settings["packet_tracer_home"]) / "bin" / "meta.exe")
    assert "<NAME>Packet Tracer MCP</NAME>" in metadata
    assert "<DESCRIPTION>Local MCP connector for Cisco Packet Tracer.</DESCRIPTION>" in metadata
    assert "<ID>org.previous.connector</ID>" in metadata
    assert "<KEY>existing-secret</KEY>" in metadata
    assert list(destination.parent.iterdir()) == [destination]


def test_failed_registration_compilation_removes_temporary_secret(isolated_install, monkeypatch):
    def fail(arguments, **kwargs):
        raise RuntimeError("simulated Cisco failure")

    monkeypatch.setattr(installer, "run", fail)
    with pytest.raises(RuntimeError, match="simulated Cisco failure"):
        installer.compile_registration({"app_id": "org.previous.connector", "secret": "private", "packet_tracer_home": "offline"}, isolated_install / "extension")
    assert list(((isolated_install / "extension") / "registration").iterdir()) == []


def offline_main(isolated_install, monkeypatch, *, install_root=None, packet_tracer=None):
    archive = make_archive(isolated_install, monkeypatch)
    packet_tracer = packet_tracer or packet_tracer_folder(isolated_install / "Packet Tracer")
    monkeypatch.setenv("ProgramFiles", str(isolated_install / "uninstalled"))
    monkeypatch.delenv("ProgramFiles(x86)", raising=False)
    commands = []
    lookups = []
    uv = isolated_install / "uv.exe"

    def find_command(name):
        lookups.append(name)
        assert name == "uv", "Only the Python environment manager may be discovered"
        return uv

    def run(arguments, *, capture=False):
        commands.append(arguments)
        executable = Path(arguments[0])
        if executable == uv:
            if arguments[1] == "venv":
                python = Path(arguments[-1]) / "Scripts" / "python.exe"
                python.parent.mkdir(parents=True)
                python.write_bytes(b"offline Python placeholder")
            else:
                assert arguments[1:3] == ["pip", "install"]
        elif executable.name == "pktctl.exe":
            assert arguments[1:] == ["--version"]
            return subprocess.CompletedProcess(arguments, 0, stdout=f"pktctl {installer.VERSION}\n")
        elif executable == packet_tracer / "bin" / "meta.exe":
            Path(arguments[1]).write_bytes(b"compiled registration" * 10)
        else:
            pytest.fail(f"Unexpected external command: {executable.name}")
        return subprocess.CompletedProcess(arguments, 0, stdout="")

    arguments = ["install.py", "--archive", str(archive)]
    if install_root is not None:
        arguments.extend(["--install-dir", str(install_root)])
    if not (install_root and (install_root / "settings.json").is_file()):
        arguments.extend(["--packet-tracer-home", str(packet_tracer)])
    monkeypatch.setattr(installer, "find_command", find_command)
    monkeypatch.setattr(installer, "run", run)
    monkeypatch.setattr(installer.sys, "argv", arguments)
    assert installer.main() == 0
    return commands, lookups


def assert_portable_install(root):
    fragment = json.loads((root / "mcp-config.json").read_text(encoding="utf-8"))
    assert fragment == {"mcpServers": {"packettracer": {
        "command": str((root / ".venv" / "Scripts" / "python.exe").resolve()),
        "args": [str((root / "server.py").resolve()), "--settings", str((root / "settings.json").resolve())],
    }}}
    assert (root / "skills" / "packettracer-tp" / "SKILL.md").read_bytes() == (installer.SOURCE / "SKILL.md").read_bytes()
    assert (root / "registration" / "packettracer-mcp.pta").is_file()
    assert (root / "doctor.py").read_bytes() == (installer.SOURCE / "doctor.py").read_bytes()
    for source in (installer.SOURCE / "docs").glob("*"):
        if source.is_file() and source.suffix in (".md", ".json"):
            assert (root / "docs" / source.name).read_bytes() == source.read_bytes()


def test_main_default_install_is_client_independent(isolated_install, monkeypatch, capsys):
    home = installer.HOME
    client_files = {
        home / ".client-one" / "config.toml": b'theme = "existing"\n',
        home / ".client-two" / "config.toml": b'profile = "existing"\n',
        home / "AppData" / "Roaming" / "ClientThree" / "config.json": b'{"existing":true}\n',
    }
    for path, content in client_files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    commands, lookups = offline_main(isolated_install, monkeypatch)
    root = isolated_install / "localappdata" / "PacketTracerMCP"
    assert installer.default_install_root() == root.resolve()
    assert_portable_install(root)
    settings = json.loads((root / "settings.json").read_text(encoding="utf-8"))
    assert settings["app_id"] == "local.packettracer.mcp"
    assert len(settings["secret"]) == 64
    assert lookups == ["uv"]
    assert {Path(command[0]).name for command in commands} <= {"uv.exe", "pktctl.exe", "meta.exe"}
    assert {path: path.read_bytes() for path in home.rglob("*") if path.is_file()} == client_files
    streams = capsys.readouterr()
    output = json.loads(streams.out)
    assert output["installed"] == str(root.resolve())
    assert output["mcp_config"] == str(root / "mcp-config.json")
    assert "secret" not in output and settings["secret"] not in json.dumps(output)
    assert output["expected_tools"] == 87
    assert str(root / "doctor.py") in output["doctor_command"]
    assert "[1/5]" in streams.err and "[5/5]" in streams.err
    assert settings["secret"] not in streams.err


def test_default_root_falls_back_to_local_app_data(isolated_install, monkeypatch):
    monkeypatch.delenv("LOCALAPPDATA")
    assert installer.default_install_root() == (installer.HOME / "AppData" / "Local" / "PacketTracerMCP").resolve()


@pytest.mark.parametrize("relative", [False, True])
def test_main_explicit_install_root(isolated_install, monkeypatch, relative):
    monkeypatch.chdir(isolated_install)
    requested = Path("custom install") if relative else isolated_install / "custom install"
    root = isolated_install / "custom install"
    offline_main(isolated_install, monkeypatch, install_root=requested)
    assert_portable_install(root)
    assert not installer.default_install_root().exists()


def test_main_preserves_existing_credentials_and_settings(isolated_install, monkeypatch):
    root = isolated_install / "existing install"
    root.mkdir()
    packet_tracer = packet_tracer_folder(isolated_install / "Packet Tracer")
    settings = {
        "app_id": "org.previous.connector", "secret": "existing-secret",
        "address": "127.0.0.1:39099", "downloads": "custom downloads",
        "workspace": "custom workspace", "packet_tracer_home": str(packet_tracer),
        "custom_setting": {"keep": True},
    }
    original = (json.dumps(settings, separators=(",", ":")) + "\n").encode("utf-8-sig")
    (root / "settings.json").write_bytes(original)
    offline_main(isolated_install, monkeypatch, install_root=root, packet_tracer=packet_tracer)
    assert (root / "settings.json").read_bytes() == original
    assert_portable_install(root)


def test_new_settings_do_not_overwrite_concurrent_credentials(isolated_install):
    path = isolated_install / "settings.json"
    concurrent = b'{"secret":"created-concurrently"}\n'
    path.write_bytes(concurrent)
    with pytest.raises(FileExistsError):
        installer.save_settings(path, None, {"secret": "replacement"})
    assert path.read_bytes() == concurrent


def test_private_credentials_restrict_windows_acl(isolated_install, monkeypatch):
    calls = []
    monkeypatch.setenv("USERNAME", "local-user")
    monkeypatch.setenv("USERDOMAIN", "LOCAL")
    monkeypatch.setattr(installer, "run", lambda arguments, **kwargs: calls.append((arguments, kwargs)))
    path = isolated_install / "credentials.json"
    private_file(path)
    assert calls == [(["icacls", str(path), "/inheritance:r", "/grant:r", "LOCAL\\local-user:(F)", "*S-1-5-18:(F)"], {"capture": True})]


def preflight_inputs(root, monkeypatch):
    archive = make_archive(root, monkeypatch)
    packet_tracer = packet_tracer_folder(root / "Packet Tracer")
    monkeypatch.setattr(installer, "find_command", lambda name: root / "uv.exe")
    monkeypatch.setattr(installer.platform, "machine", lambda: "AMD64")
    monkeypatch.delenv("PROCESSOR_ARCHITEW6432", raising=False)
    return argparse.Namespace(archive=archive, install_dir=root / "new installation",
                              packet_tracer_home=str(packet_tracer), check=True)


def forbid_installation_writes(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Preflight attempted an installation write or external action")

    monkeypatch.setattr(installer, "run", forbidden)
    monkeypatch.setattr(installer, "atomic_write", forbidden)
    monkeypatch.setattr(installer.os, "mkdir", forbidden)
    monkeypatch.setattr(installer.secrets, "token_hex", forbidden)
    monkeypatch.setattr(installer.tempfile, "TemporaryDirectory", forbidden)
    monkeypatch.setattr(installer.urllib.request, "urlopen", forbidden)


@pytest.mark.parametrize("use_archive", [False, True])
def test_check_is_read_only_and_json_safe(isolated_install, monkeypatch, capsys, use_archive):
    args = preflight_inputs(isolated_install, monkeypatch)
    arguments = ["install.py", "--check", "--install-dir", str(args.install_dir),
                 "--packet-tracer-home", args.packet_tracer_home]
    if use_archive:
        arguments.extend(["--archive", str(args.archive)])
    monkeypatch.setattr(installer.sys, "argv", arguments)
    before = {path: path.read_bytes() for path in isolated_install.rglob("*") if path.is_file()}
    forbid_installation_writes(monkeypatch)
    assert installer.main() == 0
    streams = capsys.readouterr()
    output = json.loads(streams.out)
    assert output["check"] == "passed" and output["expected_tools"] == 87
    assert output["existing_settings"] is False
    assert "secret" not in streams.out
    assert "No files were changed" in streams.err
    assert not args.install_dir.exists()
    assert {path: path.read_bytes() for path in isolated_install.rglob("*") if path.is_file()} == before


@pytest.mark.parametrize("machine,bits,os_arch", [
    ("ARM64", 8, None), ("AMD64", 4, None), ("x86", 4, None), ("AMD64", 8, "ARM64"),
])
def test_preflight_rejects_non_x64_before_side_effects(isolated_install, monkeypatch, machine, bits, os_arch):
    args = preflight_inputs(isolated_install, monkeypatch)
    monkeypatch.setattr(installer.platform, "machine", lambda: machine)
    monkeypatch.setattr(installer.struct, "calcsize", lambda _: bits)
    if os_arch:
        monkeypatch.setenv("PROCESSOR_ARCHITEW6432", os_arch)
    forbid_installation_writes(monkeypatch)
    with pytest.raises(RuntimeError, match="Windows x64"):
        installer.preflight(args)


def test_preflight_rejects_old_python_before_side_effects(isolated_install, monkeypatch):
    args = preflight_inputs(isolated_install, monkeypatch)
    monkeypatch.setattr(installer.sys, "version_info", (3, 11, 9))
    forbid_installation_writes(monkeypatch)
    with pytest.raises(RuntimeError, match="Python 3.12 or newer"):
        installer.preflight(args)


@pytest.mark.parametrize("payload,field", [
    (b'{"secret":"never-print-this",', "valid UTF-8 JSON"),
    (b'["never-print-this"]', "JSON object"),
    (b'{"app_id":"valid","secret":"never print this"}', "secret"),
    (b'{"app_id":"valid","secret":"never-print-this","downloads":3}', "downloads"),
])
def test_preflight_rejects_invalid_existing_settings_without_disclosing_values(isolated_install, monkeypatch, payload, field):
    args = preflight_inputs(isolated_install, monkeypatch)
    args.install_dir.mkdir()
    settings_path = args.install_dir / "settings.json"
    settings_path.write_bytes(payload)
    forbid_installation_writes(monkeypatch)
    with pytest.raises(RuntimeError, match=field) as error:
        installer.preflight(args)
    assert "never" not in str(error.value)
    assert settings_path.read_bytes() == payload
    assert list(args.install_dir.iterdir()) == [settings_path]


@pytest.mark.parametrize("relation", ["equal", "workspace_inside", "downloads_inside"])
def test_preflight_rejects_overlapping_roots_before_writes(isolated_install, monkeypatch, relation):
    args = preflight_inputs(isolated_install, monkeypatch)
    args.install_dir.mkdir()
    downloads = isolated_install / "downloads"
    workspace = downloads if relation == "equal" else downloads / "workspace"
    if relation == "downloads_inside":
        downloads, workspace = workspace, downloads
    payload = json.dumps({"app_id": "valid", "secret": "never-print-this", "downloads": str(downloads), "workspace": str(workspace)})
    (args.install_dir / "settings.json").write_text(payload, encoding="utf-8")
    forbid_installation_writes(monkeypatch)
    with pytest.raises(RuntimeError, match="must be separate"):
        installer.preflight(args)
    assert (args.install_dir / "settings.json").read_text(encoding="utf-8") == payload


@pytest.mark.parametrize("kind", ["missing", "directory", "checksum", "contents", "corrupt"])
def test_preflight_rejects_archive_input_before_installation(isolated_install, monkeypatch, kind):
    args = preflight_inputs(isolated_install, monkeypatch)
    if kind == "missing":
        args.archive = isolated_install / "missing.zip"
    elif kind == "directory":
        args.archive = isolated_install
    elif kind == "checksum":
        args.archive.write_bytes(b"untrusted download")
    elif kind == "contents":
        args.archive = make_archive(isolated_install, monkeypatch, ["pktctl.exe"])
    else:
        args.archive.write_bytes(b"not a ZIP")
        monkeypatch.setattr(installer, "ARCHIVE_SHA256", installer.fingerprint(args.archive))
    forbid_installation_writes(monkeypatch)
    with pytest.raises(RuntimeError):
        installer.preflight(args)
    assert not args.install_dir.exists()


@pytest.mark.parametrize("file_is_parent", [False, True])
def test_preflight_rejects_file_as_install_root_or_parent(isolated_install, monkeypatch, file_is_parent):
    args = preflight_inputs(isolated_install, monkeypatch)
    invalid = isolated_install / "file"
    invalid.write_bytes(b"keep")
    args.install_dir = invalid / "child" if file_is_parent else invalid
    forbid_installation_writes(monkeypatch)
    with pytest.raises(RuntimeError, match="installation path"):
        installer.preflight(args)
    assert invalid.read_bytes() == b"keep"


def test_preflight_missing_uv_is_actionable_without_side_effects(isolated_install, monkeypatch):
    args = preflight_inputs(isolated_install, monkeypatch)
    monkeypatch.setattr(installer, "find_command", find_command_original)
    monkeypatch.setattr(installer.shutil, "which", lambda _: None)
    forbid_installation_writes(monkeypatch)
    with pytest.raises(RuntimeError, match="https://docs.astral.sh/uv/getting-started/installation/"):
        installer.preflight(args)
    assert not args.install_dir.exists()


def test_preflight_missing_payload_is_actionable_before_writes(isolated_install, monkeypatch):
    args = preflight_inputs(isolated_install, monkeypatch)
    source = isolated_install / "incomplete source"
    source.mkdir()
    monkeypatch.setattr(installer, "SOURCE", source)
    forbid_installation_writes(monkeypatch)
    with pytest.raises(RuntimeError, match="Extract the complete project archive"):
        installer.preflight(args)
    assert not args.install_dir.exists()


@pytest.mark.parametrize("relative,is_directory", [
    (".venv", False), ("vendor", False), ("docs", False), ("server.py", True),
])
def test_preflight_rejects_conflicting_install_destinations_before_writes(isolated_install, monkeypatch, relative, is_directory):
    args = preflight_inputs(isolated_install, monkeypatch)
    args.install_dir.mkdir()
    conflict = args.install_dir / relative
    if is_directory:
        conflict.mkdir()
    else:
        conflict.write_bytes(b"preserve this file")
    forbid_installation_writes(monkeypatch)
    with pytest.raises(RuntimeError, match="installation"):
        installer.preflight(args)
    if not is_directory:
        assert conflict.read_bytes() == b"preserve this file"


def test_uncaptured_child_output_goes_to_stderr(monkeypatch):
    calls = []
    monkeypatch.setattr(installer.subprocess, "run", lambda *args, **kwargs: calls.append(kwargs))
    installer.run(["uv", "pip", "install"])
    assert calls[0]["stdout"] is sys.stderr
    assert calls[0]["stderr"] is sys.stderr
    assert calls[0]["capture_output"] is False


@pytest.mark.parametrize("mode", ["check_missing_python", "bootstrap", "unsupported_architecture"])
def test_powershell_bootstrap_branches_use_only_mock_commands(tmp_path, mode):
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if not powershell:
        pytest.skip("PowerShell is not available")

    def quoted(value):
        return "'" + str(value).replace("'", "''") + "'"

    uv_log = tmp_path / "uv-arguments.jsonl"
    fake_python = tmp_path / "fake-python.ps1"
    fake_python.write_text(
        "[pscustomobject]@{mock_python=$true; arguments=@($args)} | ConvertTo-Json -Compress\n"
        "$global:LASTEXITCODE = 0\n", encoding="utf-8")
    fake_uv = tmp_path / "fake-uv.ps1"
    fake_uv.write_text(
        f"ConvertTo-Json -InputObject @($args) -Compress | Add-Content -LiteralPath {quoted(uv_log)}\n"
        f"if ($args[1] -eq 'find') {{ Write-Output {quoted(fake_python)} }}\n"
        "else { Write-Output 'mock Python setup progress' }\n"
        "$global:LASTEXITCODE = 0\n", encoding="utf-8")
    wrapper = installer.SOURCE / "install.ps1"
    harness = tmp_path / "harness.ps1"
    architecture = "ARM64" if mode == "unsupported_architecture" else "AMD64"
    check_argument = " -Check" if mode == "check_missing_python" else ""
    harness.write_text(
        f"$env:OS = 'Windows_NT'\n$env:PROCESSOR_ARCHITECTURE = '{architecture}'\n"
        "$env:PROCESSOR_ARCHITEW6432 = ''\n"
        f"$env:APPDATA = {quoted(tmp_path / 'empty-appdata')}\n"
        f"$env:UV_PYTHON_INSTALL_DIR = {quoted(tmp_path / 'empty-managed')}\n"
        "function Get-Command { [CmdletBinding()] param([string]$Name)\n"
        f" if ($Name -eq 'uv') {{ [pscustomobject]@{{Source={quoted(fake_uv)}}} }}\n}}\n"
        f"try {{ & {quoted(wrapper)}{check_argument}; exit 0 }}\n"
        "catch { [Console]::Error.WriteLine($_.Exception.Message); exit 7 }\n", encoding="utf-8")
    result = subprocess.run([powershell, "-NoProfile", "-File", str(harness)], capture_output=True,
                            text=True, encoding="utf-8", errors="replace", creationflags=installer.NO_WINDOW)
    if mode == "bootstrap":
        assert result.returncode == 0, result.stderr
        report = json.loads(result.stdout)
        assert report["mock_python"] is True
        assert report["arguments"] == ["-B", str(wrapper.with_name("install.py"))]
        calls = [json.loads(line) for line in uv_log.read_text(encoding="utf-8-sig").splitlines()]
        assert calls == [["python", "install", "--no-bin", "--no-registry", "3.12"],
                         ["python", "find", "--no-project", "--no-python-downloads", "3.12"]]
        assert "mock Python setup progress" in result.stderr
    else:
        assert result.returncode == 7
        assert not uv_log.exists()
        expected = "uv python install 3.12" if mode == "check_missing_python" else "Windows x64"
        assert expected in result.stderr
