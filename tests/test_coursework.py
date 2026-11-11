from pathlib import Path
import sys

import pytest
from docx import Document

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coursework import LabFiles, plan_vlsm


@pytest.fixture
def labs(tmp_path):
    downloads = tmp_path / "Téléchargements"
    downloads.mkdir()
    return LabFiles(downloads, tmp_path / "TP" )


def test_working_copies_keep_original_bytes_and_have_unique_paths(labs):
    source = labs.downloads / "SF8 - Réseau.pka"
    source.write_bytes(b"opaque-pka-file\x00\xff")
    first = labs.prepare(str(source))
    second = labs.prepare(str(source))
    assert first["working_file"] != second["working_file"]
    Path(first["working_file"]).write_bytes(b"student changes")
    assert source.read_bytes() == b"opaque-pka-file\x00\xff"
    assert Path(second["working_file"]).read_bytes() == source.read_bytes()
    assert first["sha256"] == second["sha256"]


def test_read_cannot_leave_authorized_roots(labs, tmp_path):
    outside = tmp_path / "private.txt"
    outside.write_text("private", encoding="utf-8")
    with pytest.raises(ValueError):
        labs.resolve_read(str(labs.downloads / ".." / "private.txt"))


def test_sources_are_never_write_targets(labs):
    with pytest.raises(ValueError):
        labs.resolve_write(str(labs.downloads / "original.pka"))
    assert labs.resolve_write("rendu.pka") == labs.workspace / "rendu.pka"
    with pytest.raises(ValueError):
        labs.resolve_write("../escape.txt")


def test_docx_includes_table_addresses_and_paginated_text(labs):
    path = labs.downloads / "consignes.docx"
    doc = Document()
    doc.add_paragraph("Configurer selon le tableau.")
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "R1"
    table.cell(0, 1).text = "192.168.10.1/24"
    doc.save(path)
    result = labs.read(str(path))
    assert "192.168.10.1/24" in result["text"]
    partial = labs.read(str(path), offset=5, max_chars=12)
    assert partial["text"] == result["text"][5:17]
    assert partial["next_offset"] == 17


def test_binary_activity_is_not_treated_as_course_text(labs):
    path = labs.downloads / "activity.pka"
    path.write_bytes(b"not-a-text-format")
    with pytest.raises(ValueError, match="activity_instructions"):
        labs.read(str(path))


def test_vlsm_allocates_large_lan_first_without_overlap():
    result = plan_vlsm("192.168.40.0/24", [
        {"name": "WAN", "hosts": 2},
        {"name": "Élèves", "hosts": 60},
        {"name": "Professeurs", "hosts": 25},
    ])
    assert [row["network"] for row in result["subnets"]] == [
        "192.168.40.0/26", "192.168.40.64/27", "192.168.40.96/30",
    ]
    assert result["subnets"][0]["first_host"] == "192.168.40.1"
    assert result["subnets"][0]["last_host"] == "192.168.40.62"
    assert result["subnets"][0]["broadcast"] == "192.168.40.63"


def test_vlsm_rejects_insufficient_address_space_and_invalid_sizes():
    with pytest.raises(ValueError):
        plan_vlsm("192.0.2.0/30", [{"name": "LAN", "hosts": 10}])
    for hosts in (0, -1, 1.5, True):
        with pytest.raises(ValueError):
            plan_vlsm("192.0.2.0/24", [{"name": "LAN", "hosts": hosts}])


def test_root_containment_cannot_allow_writing_originals(tmp_path):
    for downloads, workspace in ((tmp_path / "downloads", tmp_path), (tmp_path, tmp_path / "workspace")):
        with pytest.raises(ValueError):
            LabFiles(downloads, workspace)


def test_read_rejects_symlink_outside_roots(labs, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("private", encoding="utf-8")
    link = labs.downloads / "linked.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Windows does not allow symbolic links in this session.")
    with pytest.raises(ValueError):
        labs.read(str(link))


def test_pdf_pages_without_text_are_reported(labs):
    from pypdf import PdfWriter

    path = labs.downloads / "scan.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with path.open("wb") as stream:
        writer.write(stream)
    result = labs.read(str(path))
    assert result["pages"] == 1
    assert result["warnings"] and "OCR" in result["warnings"][0]


def test_list_matches_normalized_accents_and_rejects_unsupported_files(labs):
    (labs.downloads / "Re\u0301seau-TP.PKA").write_bytes(b"pka")
    (labs.downloads / "CV.docx").write_bytes(b"not-opened-by-listing")
    (labs.downloads / "reseau.exe").write_bytes(b"exe")
    result = labs.list_labs("réseau")
    assert result["total"] == 1
    assert result["files"][0]["kind"] == "pka"


def test_reports_stay_in_workspace_and_do_not_overwrite_by_default(labs):
    first = labs.save_report("TP1/rapport.md", "# Vérifications\nPing réussi")
    assert Path(first["path"]).read_text(encoding="utf-8") == "# Vérifications\nPing réussi"
    with pytest.raises(FileExistsError):
        labs.save_report("TP1/rapport.md", "replacement")
    with pytest.raises(ValueError):
        labs.save_report(str(labs.downloads / "consigne.txt"), "replacement")


def test_invalid_pagination_is_rejected_before_reading(labs):
    for kwargs in ({"offset": -1}, {"offset": True}, {"max_chars": 0}, {"max_chars": 100001}):
        with pytest.raises(ValueError):
            labs.read("does-not-exist.txt", **kwargs)


def test_vlsm_rejects_duplicate_names_ipv6_and_network_host_bits():
    for network, lans in (
        ("2001:db8::/48", [{"name": "LAN", "hosts": 10}]),
        ("192.0.2.1/24", [{"name": "LAN", "hosts": 10}]),
        ("192.0.2.0/24", [{"name": "LAN", "hosts": 10}, {"name": "LAN", "hosts": 10}]),
    ):
        with pytest.raises(ValueError):
            plan_vlsm(network, lans)
