import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

spec = importlib.util.spec_from_file_location("packettracer_install", Path(__file__).resolve().parents[1] / "install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def test_native_windows_output_with_oem_bytes_is_captured():
    result = installer.run([sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'install\\x82')"], capture=True)
    assert isinstance(result.stdout, str) and result.stdout.startswith("install")


@pytest.fixture
def isolated_install(tmp_path, monkeypatch):
    """Keep all installer operations inside pytest's temporary directory."""
    monkeypatch.setattr(installer, "HOME", tmp_path / "home")
    monkeypatch.setattr(installer, "EXTENSION", tmp_path / "extension")
    monkeypatch.setattr(installer, "CONFIG", tmp_path / "config.toml")
    monkeypatch.setattr(installer, "SKILL", tmp_path / "SKILL.md")

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


def registration_config(python, *, command=None, duplicate=False):
    entry = {
        "name": "packettracer", "transport": "stdio", "command": str(command or python),
        "args": [str(installer.EXTENSION / "server.py")],
        "startup_timeout_sec": 20, "tool_timeout_sec": 180,
    }
    table = "\n[[mcp_servers]]\n" + "\n".join(f"{key} = {json.dumps(value)}" for key, value in entry.items()) + "\n"
    return ("theme = \"existing\"\n" + table * (2 if duplicate else 1)).encode("utf-8")


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
        installer.install_vendor(archive)
    assert not installer.EXTENSION.exists()


@pytest.mark.parametrize("names", [
    ["pktctl.exe", "LICENSE", "README.md"],
    ["pktctl.exe", "LICENSE", "README.md", "CHANGELOG.md", "CHANGELOG.md"],
])
def test_invalid_archive_preserves_existing_vendor_files(isolated_install, monkeypatch, names):
    archive = make_archive(isolated_install, monkeypatch, names)
    existing = installer.EXTENSION / "vendor" / "pktctl.exe"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"previous engine")
    with pytest.raises(RuntimeError, match="Unexpected archive contents"):
        installer.install_vendor(archive)
    assert {path.name: path.read_bytes() for path in existing.parent.iterdir()} == {"pktctl.exe": b"previous engine"}


def test_corrupt_zip_is_rejected_before_writes(isolated_install, monkeypatch):
    archive = isolated_install / "corrupt.zip"
    archive.write_bytes(b"not a ZIP file")
    monkeypatch.setattr(installer, "ARCHIVE_SHA256", installer.fingerprint(archive))
    with pytest.raises(zipfile.BadZipFile):
        installer.install_vendor(archive)
    assert not installer.EXTENSION.exists()


def test_verified_archive_checks_exact_engine_version(isolated_install, monkeypatch):
    archive = make_archive(isolated_install, monkeypatch)
    calls = []

    def version(arguments, *, capture=False):
        calls.append((arguments, capture))
        return subprocess.CompletedProcess(arguments, 0, stdout=f"pktctl {installer.VERSION}\n")

    monkeypatch.setattr(installer, "run", version)
    installer.install_vendor(archive)
    assert calls == [([str(installer.EXTENSION / "vendor" / "pktctl.exe"), "--version"], True)]
    for name in ("pktctl.exe", "LICENSE", "README.md", "CHANGELOG.md"):
        assert (installer.EXTENSION / "vendor" / name).read_bytes() == name.encode("ascii")


@pytest.mark.parametrize("reported", ["pktctl 0.2.1", "pktctl 0.2.2\nextra output"])
def test_wrong_engine_version_is_rejected(isolated_install, monkeypatch, reported):
    archive = make_archive(isolated_install, monkeypatch)
    monkeypatch.setattr(installer, "run", lambda args, **kwargs: subprocess.CompletedProcess(args, 0, stdout=reported))
    with pytest.raises(RuntimeError, match="expected version"):
        installer.install_vendor(archive)


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
    path = installer.EXTENSION / "settings.json"
    settings = {"app_id": "local.vibe.packettracer.tp", "secret": "existing-secret"}
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
        "app_id": "local.vibe.packettracer.tp", "secret": "existing-secret",
        "packet_tracer_home": str(isolated_install / "packet tracer"),
    }

    def compile_meta(arguments, *, capture=False):
        captured.append((arguments, Path(arguments[2]).read_text(encoding="utf-8")))
        Path(arguments[1]).write_bytes(b"compiled registration" * 10)

    monkeypatch.setattr(installer, "run", compile_meta)
    destination = installer.compile_registration(settings)
    assert destination.name == "vibe-packettracer.pta"
    arguments, metadata = captured[0]
    assert arguments[0] == str(Path(settings["packet_tracer_home"]) / "bin" / "meta.exe")
    assert "<NAME>Packet Tracer MCP</NAME>" in metadata
    assert "<DESCRIPTION>Local MCP connector for Cisco Packet Tracer.</DESCRIPTION>" in metadata
    assert "<ID>local.vibe.packettracer.tp</ID>" in metadata
    assert "<KEY>existing-secret</KEY>" in metadata
    assert list(destination.parent.iterdir()) == [destination]


def test_failed_registration_compilation_removes_temporary_secret(isolated_install, monkeypatch):
    def fail(arguments, **kwargs):
        raise RuntimeError("simulated Cisco failure")

    monkeypatch.setattr(installer, "run", fail)
    with pytest.raises(RuntimeError, match="simulated Cisco failure"):
        installer.compile_registration({"app_id": "local.vibe.packettracer.tp", "secret": "private", "packet_tracer_home": "offline"})
    assert list((installer.EXTENSION / "registration").iterdir()) == []


def test_changed_vibe_config_is_preserved_before_registration(isolated_install):
    installer.CONFIG.write_bytes(b'theme = "original"\n')
    initial = installer.fingerprint(installer.CONFIG)
    concurrent = b'theme = "concurrent"\n'
    installer.CONFIG.write_bytes(concurrent)
    with pytest.raises(RuntimeError, match="changed during installation"):
        installer.register_vibe(isolated_install / "python.exe", initial)
    assert installer.CONFIG.read_bytes() == concurrent
    assert not list(isolated_install.glob("*.bak"))


def test_matching_vibe_registration_is_a_noop(isolated_install):
    python = isolated_install / "python.exe"
    original = registration_config(python)
    installer.CONFIG.write_bytes(original)
    assert installer.register_vibe(python, installer.fingerprint(installer.CONFIG)) == "already_registered"
    assert installer.CONFIG.read_bytes() == original
    assert not list(isolated_install.glob("*.bak"))


@pytest.mark.parametrize("duplicate", [False, True])
def test_conflicting_or_duplicate_registration_is_preserved(isolated_install, duplicate):
    python = isolated_install / "python.exe"
    original = registration_config(python, command=python if duplicate else isolated_install / "other.exe", duplicate=duplicate)
    installer.CONFIG.write_bytes(original)
    with pytest.raises(RuntimeError, match="different Vibe packettracer entry"):
        installer.register_vibe(python, installer.fingerprint(installer.CONFIG))
    assert installer.CONFIG.read_bytes() == original
    assert not list(isolated_install.glob("*.bak"))


def test_edit_just_before_native_registration_prevents_command(isolated_install, monkeypatch):
    original = b'theme = "original"\n'
    concurrent = b'theme = "concurrent"\n'
    installer.CONFIG.write_bytes(original)
    initial = installer.fingerprint(installer.CONFIG)
    monkeypatch.setattr(installer, "find_command", lambda name: isolated_install / "vibe.exe")
    monkeypatch.setattr(installer, "private_file", lambda path: installer.CONFIG.write_bytes(concurrent))
    with pytest.raises(RuntimeError, match="just before registration"):
        installer.register_vibe(isolated_install / "python.exe", initial)
    assert installer.CONFIG.read_bytes() == concurrent
    assert [path.read_bytes() for path in isolated_install.glob("*.bak")] == [original]


def test_failed_native_registration_verification_preserves_current_config(isolated_install, monkeypatch):
    original = b'theme = "original"\n'
    current = b'theme = "concurrent"\n# native registration did not create the expected entry\n'
    installer.CONFIG.write_bytes(original)
    initial = installer.fingerprint(installer.CONFIG)
    monkeypatch.setattr(installer, "find_command", lambda name: isolated_install / "vibe.exe")
    monkeypatch.setattr(installer, "run", lambda args, **kwargs: installer.CONFIG.write_bytes(current))
    with pytest.raises(RuntimeError, match="could not be verified"):
        installer.register_vibe(isolated_install / "python.exe", initial)
    assert installer.CONFIG.read_bytes() == current
    assert [path.read_bytes() for path in isolated_install.glob("*.bak")] == [original]
