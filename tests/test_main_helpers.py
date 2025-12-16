import pytest


def test_normalize_arc_path_replaces_backslashes(m):
    assert m._normalize_arc_path("dir\\file.txt") == "dir/file.txt"


def test_safe_join_prevents_traversal(tmp_path, m):
    base = tmp_path / "dest"
    base.mkdir()
    safe = m._safe_join(str(base), "sub/file.txt")
    assert safe.startswith(str(base))
    with pytest.raises(ValueError):
        _ = m._safe_join(str(base), "../../etc/passwd")


def test_fmt_pct_and_bytes(m):
    assert m._fmt_pct(0, 0) == "0%"
    assert m._fmt_pct(50, 100).strip().endswith("%")
    assert m._fmt_pct(10, 10).strip().startswith("100")

    assert m._fmt_bytes(0) == "0.00 B"
    assert m._fmt_bytes(1024).endswith("KiB")


def test_perfileprogress_calls_bucketed(no_progress, m):
    p = m.PerFileProgress("Archiving", "x.txt", 0, 100)
    p(0, 100)
    p(0, 100)
    p(10, 100)
    p(10, 100)
    p(19, 100)
    p(19, 100)
    assert len(no_progress) == 3
    assert all("Overall" in line for line in no_progress)


def test_iter_entries_scans_tree(temp_tree, m):
    entries = m._iter_entries([str(temp_tree)])
    assert any(p.endswith("rootdir") and e[2] for e in entries for p in [e[0]])
    assert any("rootdir/sub" == e[0] and e[2] for e in entries)
    assert any("rootdir/a.txt" == e[0] and not e[2] for e in entries)
    assert any("rootdir/sub/b.bin" == e[0] and not e[2] for e in entries)


def test_iter_entries_nonexistent_raises(tmp_path, m):
    with pytest.raises(FileNotFoundError):
        _ = m._iter_entries([str(tmp_path / "nope.txt")])


def test_cli_parser_accepts_subcommands(m):
    parser = m.get_parser()
    ns = parser.parse_args(["archive", "file1", "-o", "out.ar"])
    assert ns.cmd in ("archive", "a")
    ns2 = parser.parse_args(["unarchive", "in.ar", "-o", "dest"])
    assert ns2.cmd in ("unarchive", "u")
