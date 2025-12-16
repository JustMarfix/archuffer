import argparse
import os
import struct
import stat as _stat
import sys

from typing import List, Tuple
from archiver import Archiver

MAGIC = b"ARH1"  #: Archuffer magic number
VERSION = 2  #: Current archuffer version


def get_parser():
    """Create and configure the CLI argument parser.

    :returns: Configured argument parser.
    :rtype: argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser(
        description="Huffman-based archiver for multiple files/directories"
    )
    subparsers = parser.add_subparsers(
        title="subcommands", dest="cmd", required=True
    )

    archive = subparsers.add_parser(
        "archive", aliases=["a"], help="Archive and compress files/directories"
    )
    archive.add_argument(
        "target",
        nargs="+",
        help="Files or directories to archive (recursively)",
    )
    archive.add_argument(
        "-o", "--output", required=True, help="Output archive file path"
    )
    archive.add_argument(
        "-P",
        "--no-progress",
        action="store_true",
        help="Show per-file and overall progress",
    )

    unarchive = subparsers.add_parser(
        "unarchive", aliases=["u"], help="Decompress and unarchive data"
    )
    unarchive.add_argument("archive", help="Archive file to extract")
    unarchive.add_argument(
        "-o",
        "--output",
        default=".",
        help="Destination directory (default: current)",
    )
    unarchive.add_argument(
        "-P",
        "--no-progress",
        action="store_true",
        help="Show per-file and overall progress",
    )

    return parser


def _iter_entries(targets: List[str]) -> List[Tuple[str, str, bool]]:
    """
    Build a list of entries for files and directories
    to include in the archive.

    :param targets: One or more filesystem paths (files or directories).
    :type targets: List[str]
    :returns: List of entries to be archived.
    :rtype: List[Tuple[str, str, bool]]
    :raises FileNotFoundError: If any of the targets does not exist.
    """
    entries: List[Tuple[str, str, bool]] = []
    for target in targets:
        target = os.path.abspath(target)
        if not os.path.exists(target):
            raise FileNotFoundError(f"Target not found: {target}")
        base = os.path.basename(os.path.normpath(target))
        if os.path.isdir(target):
            entries.append((base, target, True))
            for root, dirs, files in os.walk(target):
                dirs.sort()
                files.sort()
                rel_root = os.path.relpath(root, start=target)
                rel_root = "" if rel_root == "." else rel_root
                for d in dirs:
                    arc_path = (
                        os.path.join(base, rel_root, d)
                        if rel_root
                        else os.path.join(base, d)
                    )
                    entries.append(
                        (
                            _normalize_arc_path(arc_path),
                            os.path.join(root, d),
                            True,
                        )
                    )
                for f in files:
                    fs_path = os.path.join(root, f)
                    arc_path = (
                        os.path.join(base, rel_root, f)
                        if rel_root
                        else os.path.join(base, f)
                    )
                    entries.append(
                        (_normalize_arc_path(arc_path), fs_path, False)
                    )
        else:
            entries.append((base, target, False))
    return entries


def _normalize_arc_path(path: str) -> str:
    """Normalize a filesystem path for storage inside the archive.

    :param path: Filesystem path.
    :type path: str
    :returns: Normalized archive path.
    :rtype: str
    """
    return path.replace("\\", "/")


def _safe_join(base: str, arc_path: str) -> str:
    """Join an archive-stored path to a base directory safely.

    Defense against path traversal attacks.

    :param base: Destination base directory.
    :type base: str
    :param arc_path: Path as stored in the archive (POSIX-style).
    :type arc_path: str
    :returns: Absolute, safe path within ``base``.
    :rtype: str
    :raises ValueError: If the joined path would escape the base directory.
    """
    base_abs = os.path.abspath(base)
    normalized = arc_path.replace("/", os.sep).replace("\\", os.sep)
    candidate = os.path.abspath(os.path.join(base_abs, normalized))
    if os.path.commonpath([candidate, base_abs]) != base_abs:
        raise ValueError(f"Unsafe path in archive: {arc_path}")
    return candidate


def _print_progress(line: str) -> None:
    """Render and flush a single progress line in-place (carriage return).

    :param line: The textual progress line to display.
    :type line: str
    :returns: None
    :rtype: None
    """
    sys.stdout.write("\r" + line)
    sys.stdout.flush()


def _fmt_pct(done: int, total: int) -> str:
    """Format a completion percentage string like ``12.34%``.

    :param done: Units completed.
    :type done: int
    :param total: Total units to complete.
    :type total: int
    :returns: Percentage.
    :rtype: str
    """
    if total <= 0:
        return "0%"
    pct = 100.0 * (done / float(total))
    return f"{pct:6.2f}%"


def _fmt_bytes(n: int) -> str:
    """Format a byte count into a human-readable string.

    :param n: Number of bytes.
    :type n: int
    :returns: Human-readable string.
    :rtype: str
    """
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti']:
        if abs(n) < 1024:
            return f"{n:.2f} {unit}B"
        n /= 1024
    return f"{n:.2f} PiB"


class PerFileProgress:
    """Callable progress reporter to avoid nested callback functions.

    Renders a single-line progress with per-file and overall percentages.

    :ivar label: Action label (e.g., "Archiving" or "Extracting").
    :type label: str
    :ivar arc_path: Path displayed for the current archive entry.
    :type arc_path: str
    :ivar overall_base: Overall bytes already completed before this file.
    :type overall_base: int
    :ivar overall_total: Total bytes across all files for the operation.
    :type overall_total: int
    """

    def __init__(
        self, label: str, arc_path: str, overall_base: int, overall_total: int
    ) -> None:
        """Initialize progress reporter for a single archive entry.

        :param label: Action label (e.g., ``"Archiving"`` or ``"Extracting"``).
        :type label: str
        :param arc_path: Path to display for the current file/dir
            inside archive.
        :type arc_path: str
        :param overall_base: Overall bytes completed before this file starts.
        :type overall_base: int
        :param overall_total: Total bytes across all files for the operation.
        :type overall_total: int
        :returns: None
        :rtype: None
        """
        self.label = label
        self.arc_path = arc_path
        self.overall_base = int(overall_base)
        self.overall_total = int(overall_total)
        self._last_reported = -1

    def __call__(self, done: int, total: int) -> None:
        """Update the progress display for the current file.

        :param done: Bytes processed for the current file.
        :type done: int
        :param total: Total bytes for the current file.
        :type total: int
        :returns: None
        :rtype: None
        """
        if total <= 0:
            return
        percent_bucket = int((done * 100) / total)
        if percent_bucket == self._last_reported:
            return
        self._last_reported = percent_bucket
        cur_overall = self.overall_base + done
        line = (
            f"{self.label} {self.arc_path}  {_fmt_pct(done, total)}"
            f"  | Overall {_fmt_pct(cur_overall, self.overall_total)}"
        )
        _print_progress(line)


def create_archive(
    targets: List[str], output_path: str, hide_progress: bool
) -> None:
    """Create an archive file from given targets (files and/or directories).

    Archive format (little-endian):
    - Magic: 'ARH1' (4 bytes)
    - Version: 1 byte
    - Entry count: uint32
    For each entry:
    - Path length: uint32
    - Path (utf-8 bytes)
    - Type: uint8 (0=file, 1=dir)
    - Metadata (since container VERSION >= 2):
    - - mode: uint32 (POSIX permission bits, see stat.S_IMODE)
    - - uid: uint32 (0xFFFFFFFF if unknown)
    - - gid: uint32 (0xFFFFFFFF if unknown)
    - If file:
    - - Compressed size: uint32
    - - Compressed data bytes (produced by Archiver.compress)

   :param hide_progress: Whether to show per-file and overall progress.
   :type hide_progress: bool
   :param targets: Filesystem targets to include
        (each file/dir is added recursively).
   :type targets: List[str]
   :param output_path: Destination archive file path.
   :type output_path: str
   :returns: None
   :rtype: None
   """
    try:
        entries = _iter_entries(targets)
    except FileNotFoundError as e:
        print('[!] You selected a file or directory that does not exist:',
              str(e).split(' ', maxsplit=3)[3])
        return
    file_entries = [e for e in entries if not e[2]]
    total_bytes = sum(os.path.getsize(e[1]) for e in file_entries)
    overall_done = 0
    total_compressed_bytes = 0
    with open(output_path, "wb") as out:
        out.write(MAGIC)
        out.write(struct.pack("<B", VERSION))
        out.write(struct.pack("<I", len(entries)))

        for arc_path, fs_path, is_dir in entries:
            arc_path_bytes = arc_path.encode("utf-8")
            out.write(struct.pack("<I", len(arc_path_bytes)))
            out.write(arc_path_bytes)
            out.write(struct.pack("<B", 1 if is_dir else 0))
            st = os.stat(fs_path, follow_symlinks=False)
            mode = _stat.S_IMODE(st.st_mode)
            uid = getattr(st, "st_uid", None)
            gid = getattr(st, "st_gid", None)
            uid_val = 0xFFFFFFFF if uid is None else int(uid) & 0xFFFFFFFF
            gid_val = 0xFFFFFFFF if gid is None else int(gid) & 0xFFFFFFFF
            out.write(struct.pack("<III", mode, uid_val, gid_val))
            if not is_dir:
                with open(fs_path, "rb") as f:
                    data = f.read()
                if not hide_progress and total_bytes > 0:
                    file_total = len(data)
                    on_prog = PerFileProgress(
                        "Archiving", arc_path, overall_done, total_bytes
                    )
                    comp = Archiver().compress(data, on_progress=on_prog)
                    overall_done += file_total
                    line = (
                        f"Archiving {arc_path}  "
                        f"{_fmt_pct(file_total, file_total)}  "
                        f"| Overall {_fmt_pct(overall_done, total_bytes)}"
                    )
                    _print_progress(line)
                else:
                    comp = Archiver().compress(data)
                total_compressed_bytes += len(comp)
                out.write(struct.pack("<I", len(comp)))
                out.write(comp)
        if not hide_progress:
            sys.stdout.write("\n")
            sys.stdout.flush()
        print("Size before compression: ", _fmt_bytes(total_bytes))
        print("Size after compression: ", _fmt_bytes(total_compressed_bytes))
        print(f"Compression ratio: {total_bytes / total_compressed_bytes:.2f}")


def extract_archive(
    archive_path: str, dest_dir: str, hide_progress: bool
) -> None:
    """Extract an archive created by ``create_archive``.

    :param archive_path: Path to the archive file to extract.
    :type archive_path: str
    :param dest_dir: Destination directory.
    :type dest_dir: str
    :param hide_progress: Whether to show per-file and overall progress.
    :type hide_progress: bool
    :returns: None
    :rtype: None
    :raises ValueError: If the archive header is invalid
        or uses an unsupported version.
    """
    dest_dir = os.path.abspath(dest_dir)
    os.makedirs(dest_dir, exist_ok=True)
    try:
        archive_fd = open(archive_path, "rb")
    except FileNotFoundError:
        print(f"[!] Archive file not found: {archive_path}")
        return
    with archive_fd as f:
        magic = f.read(4)
        if magic != MAGIC:
            raise ValueError("Invalid archive format (bad magic)")
        ver = struct.unpack("<B", f.read(1))[0]
        if ver not in (1, 2):
            raise ValueError(f"Unsupported archive version: {ver}")
        count = struct.unpack("<I", f.read(4))[0]

        total_uncompressed = 0
        if not hide_progress:
            pos_after_header = f.tell()
            for _ in range(count):
                plen = struct.unpack("<I", f.read(4))[0]
                _ = f.read(plen)  # path bytes
                typ = struct.unpack("<B", f.read(1))[0]
                if ver >= 2:
                    _ = f.read(12)  # mode, uid, gid
                if typ == 1:  # dir
                    continue
                csize = struct.unpack("<I", f.read(4))[0]
                header = f.read(min(5, csize))
                if len(header) >= 5:
                    orig_size = int.from_bytes(header[1:5], "big")
                    total_uncompressed += orig_size
                remaining = csize - len(header)
                if remaining > 0:
                    f.seek(remaining, 1)
            f.seek(pos_after_header, 0)

        overall_done = 0

        for _ in range(count):
            plen = struct.unpack("<I", f.read(4))[0]
            pbytes = f.read(plen)
            arc_path = pbytes.decode("utf-8")
            typ = struct.unpack("<B", f.read(1))[0]
            if ver >= 2:
                mode, uid_val, gid_val = struct.unpack("<III", f.read(12))
            else:
                mode, uid_val, gid_val = (
                    0o644 if typ == 0 else 0o755,
                    0xFFFFFFFF,
                    0xFFFFFFFF,
                )
            full_path = _safe_join(dest_dir, arc_path)
            if typ == 1:
                try:
                    os.makedirs(full_path, exist_ok=True)
                    os.chmod(full_path, mode)
                except PermissionError:
                    print(
                        "[!] Permission error happened "
                        f"while writing to a {arc_path}"
                    )
                if hasattr(os, "chown"):
                    uid_arg = -1 if uid_val == 0xFFFFFFFF else uid_val
                    gid_arg = -1 if gid_val == 0xFFFFFFFF else gid_val
                    if uid_arg != -1 or gid_arg != -1:
                        try:
                            os.chown(full_path, uid_arg, gid_arg)
                        except PermissionError:
                            print(
                                "[!] Permission error happened"
                                f"while trying to chown a {arc_path}"
                            )
            else:
                csize = struct.unpack("<I", f.read(4))[0]
                comp = f.read(csize)
                if not hide_progress and total_uncompressed > 0:
                    file_total = 0
                    if len(comp) >= 5:
                        file_total = int.from_bytes(comp[1:5], "big")

                    on_prog = PerFileProgress(
                        "Extracting",
                        arc_path,
                        overall_done,
                        total_uncompressed,
                    )
                    data = Archiver().decompress(comp, on_progress=on_prog)
                    overall_done += file_total
                    line = (
                        f"Extracting {arc_path}  "
                        f"{_fmt_pct(file_total, file_total)}  | Overall "
                        f"{_fmt_pct(overall_done, total_uncompressed)}"
                    )
                    _print_progress(line)
                else:
                    data = Archiver().decompress(comp)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                try:
                    with open(full_path, "wb") as out:
                        out.write(data)
                    os.chmod(full_path, mode)
                except PermissionError:
                    print(
                        "[!] Permission error happened while"
                        f"writing to a {arc_path}"
                    )
                    continue
                if hasattr(os, "chown"):
                    uid_arg = -1 if uid_val == 0xFFFFFFFF else uid_val
                    gid_arg = -1 if gid_val == 0xFFFFFFFF else gid_val
                    if uid_arg != -1 or gid_arg != -1:
                        try:
                            os.chown(full_path, uid_arg, gid_arg)
                        except PermissionError:
                            print(
                                "[!] Permission error happened "
                                f"while trying to chown a {arc_path}"
                            )
        if not hide_progress:
            sys.stdout.write("\n")
            sys.stdout.flush()


def main():
    """Entry point for the CLI tool.

    :returns: None
    :rtype: None
    """
    parser = get_parser()
    args = parser.parse_args()

    if args.cmd in ["archive", "a"]:
        create_archive(
            args.target, args.output, getattr(args, "no_progress", False)
        )
    elif args.cmd in ["unarchive", "u"]:
        extract_archive(
            args.archive, args.output, getattr(args, "no_progress", False)
        )


if __name__ == "__main__":
    main()
