"""Local course files and addressing helpers for the Packet Tracer MCP.

Reading is confined to the Downloads and working directories. Packet Tracer
activities remain opaque files: their instructions are read through Cisco IPC.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import shutil
import tempfile
import unicodedata

DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".csv"}
ACTIVITY_EXTENSIONS = {".pkt", ".pka"}
MAX_FILE_BYTES = 128 * 1024 * 1024


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _search_key(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(c))


class LabFiles:
    def __init__(self, downloads: Path, workspace: Path):
        self.downloads = downloads.resolve()
        self.workspace = workspace.resolve()
        if self.downloads.is_relative_to(self.workspace) or self.workspace.is_relative_to(self.downloads):
            raise ValueError("The working directory must be separate from Downloads.")

    @staticmethod
    def _local_path(path: str, base: Path) -> Path:
        if not isinstance(path, str) or not path.strip() or "\x00" in path:
            raise ValueError("A non-empty local path is required.")
        if path.startswith(("\\\\", "//")) or "://" in path:
            raise ValueError("Network paths and URLs are not supported.")
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = base / candidate
        return candidate.resolve()

    def resolve_read(self, path: str) -> Path:
        candidate = self._local_path(path, self.downloads)
        if not any(candidate.is_relative_to(root) for root in (self.downloads, self.workspace)):
            raise ValueError("Reading is allowed only within Downloads and the working directory.")
        if not candidate.is_file():
            raise FileNotFoundError(f"File not found: {candidate}")
        if candidate.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("The file exceeds the 128 MiB limit.")
        return candidate

    def resolve_write(self, path: str) -> Path:
        candidate = self._local_path(path, self.workspace)
        if not candidate.is_relative_to(self.workspace) or candidate == self.workspace:
            raise ValueError("Writing is allowed only within the working directory.")
        return candidate

    def prepare(self, path: str) -> dict:
        source = self.resolve_read(path)
        if source.suffix.lower() not in ACTIVITY_EXTENSIONS:
            raise ValueError("Choose a Packet Tracer .pkt or .pka file.")
        self.workspace.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^\w .-]", "_", source.stem, flags=re.UNICODE)[:30].strip(" .") or "activite"
        prefix = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + slug + "-"
        folder = Path(tempfile.mkdtemp(prefix=prefix, dir=self.workspace))
        working = self.resolve_write(str(folder / source.name))
        shutil.copy2(source, working)
        original_hash = _digest(source)
        if original_hash != _digest(working):
            raise OSError("The source changed while being copied; prepare the working copy again.")
        manifest = {
            "source": str(source), "working_file": str(working),
            "workspace": str(folder), "sha256": original_hash,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        (folder / "source-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest

    def read(self, path: str, offset: int = 0, max_chars: int = 20000) -> dict:
        if type(offset) is not int or offset < 0 or type(max_chars) is not int or not 1 <= max_chars <= 100000:
            raise ValueError("offset must be non-negative; max_chars must be between 1 and 100000.")
        source = self.resolve_read(path)
        suffix = source.suffix.lower()
        warnings = []
        pages = None
        if suffix in ACTIVITY_EXTENSIONS:
            raise ValueError("Open the .pka/.pkt copy, then use activity_instructions; this format is not text.")
        if suffix == ".pdf":
            from pypdf import PdfReader

            pdf = PdfReader(source)
            if pdf.is_encrypted and pdf.decrypt("") == 0:
                raise ValueError("The PDF is password-protected.")
            pages = len(pdf.pages)
            sections = []
            no_text = []
            for index, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""
                if not text.strip():
                    no_text.append(index)
                sections.append(f"[Page {index}]\n{text}")
            content = "\n\n".join(sections)
            if no_text:
                warnings.append("Pages without extractable text (scanned or blank pages); OCR is required to read images: " + ", ".join(map(str, no_text)))
        elif suffix == ".docx":
            from docx import Document

            sections = []
            for block in Document(source).iter_inner_content():
                if hasattr(block, "rows"):
                    sections.extend(" | ".join(cell.text for cell in row.cells) for row in block.rows)
                else:
                    sections.append(block.text)
            content = "\n".join(sections)
            warnings.append("Inspect embedded diagrams and images visually when needed for the lab.")
        elif suffix in DOCUMENT_EXTENSIONS:
            raw = source.read_bytes()
            try:
                content = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                content = raw.decode("cp1252")
                warnings.append("Text decoded using Windows-1252.")
        else:
            raise ValueError("Readable formats: PDF, DOCX, TXT, MD and CSV.")
        end = min(len(content), offset + max_chars)
        return {
            "path": str(source), "text": content[offset:end], "offset": offset,
            "next_offset": end if end < len(content) else None,
            "total_chars": len(content), "pages": pages, "warnings": warnings,
        }

    def list_labs(self, query: str = "", limit: int = 100) -> dict:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000.")
        if not isinstance(query, str):
            raise ValueError("query must be text.")
        wanted = _search_key(query)
        matches = []
        for root in (self.downloads, self.workspace):
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                if path.suffix.lower() not in DOCUMENT_EXTENSIONS | ACTIVITY_EXTENSIONS:
                    continue
                if wanted and wanted not in _search_key(path.name):
                    continue
                try:
                    resolved = self.resolve_read(str(path))
                    stat = resolved.stat()
                except (OSError, ValueError):
                    continue
                matches.append({"name": path.name, "path": str(resolved), "kind": path.suffix.lower()[1:], "bytes": stat.st_size, "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()})
        matches.sort(key=lambda row: (row["kind"] not in {"pkt", "pka"}, _search_key(row["name"]), row["path"]))
        return {"files": matches[:limit], "total": len(matches), "truncated": len(matches) > limit, "downloads": str(self.downloads), "workspace": str(self.workspace)}

    def save_report(self, path: str, content: str, overwrite: bool = False) -> dict:
        target = self.resolve_write(path)
        if target.suffix.lower() not in {".md", ".txt", ".json"}:
            raise ValueError("The report must be a .md, .txt or .json file.")
        if not isinstance(content, str) or len(content) > 2_000_000:
            raise ValueError("The report must be text with fewer than 2 million characters.")
        if target.suffix.lower() == ".json":
            json.loads(content)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation avoids accidentally replacing a previous report.
        with target.open("w" if overwrite else "x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        return {"path": str(target), "bytes": target.stat().st_size, "sha256": _digest(target)}


def plan_vlsm(network: str, lans: list[dict]) -> dict:
    """Allocate conventional IPv4 LANs, largest first, reserving network/broadcast."""
    base = ipaddress.ip_network(network, strict=True)
    if base.version != 4:
        raise ValueError("VLSM calculation requires an IPv4 network.")
    if not isinstance(lans, list) or not 1 <= len(lans) <= 1000:
        raise ValueError("Provide between 1 and 1000 subnets.")
    requests = []
    names = set()
    for index, lan in enumerate(lans):
        if not isinstance(lan, dict):
            raise ValueError("Each LAN must contain name and hosts.")
        name, hosts = lan.get("name"), lan.get("hosts")
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("Each LAN must have a non-empty, unique name.")
        if type(hosts) is not int or not 1 <= hosts <= 2**32 - 2:
            raise ValueError("hosts must be a positive integer representing the required number of hosts.")
        names.add(name)
        bits = (hosts + 1).bit_length()
        block_size = 1 << max(2, bits)
        requests.append((block_size, index, name, hosts))
    cursor = int(base.network_address)
    rows = []
    for size, index, name, hosts in sorted(requests, key=lambda item: (-item[0], item[1])):
        cursor = ((cursor + size - 1) // size) * size
        if cursor + size - 1 > int(base.broadcast_address):
            raise ValueError(f"Network {base} is too small for all LANs (allocation failed for {name}).")
        subnet = ipaddress.IPv4Network((cursor, 32 - (size.bit_length() - 1)))
        rows.append({"name": name, "requested_hosts": hosts, "network": str(subnet), "mask": str(subnet.netmask), "prefix": subnet.prefixlen, "first_host": str(subnet.network_address + 1), "last_host": str(subnet.broadcast_address - 1), "broadcast": str(subnet.broadcast_address), "usable_hosts": subnet.num_addresses - 2})
        cursor += size
    return {"network": str(base), "subnets": rows, "unallocated_addresses": int(base.broadcast_address) - cursor + 1, "convention": "IPv4 LAN: network and broadcast addresses reserved, minimum /30 (no /31)."}
