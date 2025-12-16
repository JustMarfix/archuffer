import struct
import pytest


def test_archive_and_extract_roundtrip(
        temp_tree, tmp_path, no_progress,
        fake_chown, m, collect_files_fn
):
    arc_path = tmp_path / "out.ar"
    m.create_archive([str(temp_tree)], str(arc_path), hide_progress=True)
    assert arc_path.exists() and arc_path.stat().st_size > 0

    dest = tmp_path / "extract"
    m.extract_archive(str(arc_path), str(dest), hide_progress=True)

    src_files = collect_files_fn(temp_tree)
    dst_files = collect_files_fn(dest / temp_tree.name)
    assert src_files == dst_files


def test_extract_bad_headers(tmp_path, m):
    arc = tmp_path / "bad.ar"

    with open(arc, "wb") as f:
        f.write(
            b"BAD!"  # bad magic
            + struct.pack("<B", m.VERSION)
            + struct.pack("<I", 0))
    with pytest.raises(ValueError):
        m.extract_archive(str(arc), str(tmp_path / "out1"), hide_progress=True)

    with open(arc, "wb") as f:
        f.write(
            m.MAGIC
            + struct.pack("<B", 99)  # unsupported version
            + struct.pack("<I", 0))
    with pytest.raises(ValueError):
        m.extract_archive(str(arc), str(tmp_path / "out2"), hide_progress=True)
