import argparse
import os
import struct

from typing import List, Tuple
from archiver import Archiver


MAGIC = b'ARH1'
VERSION = 1


def get_parser():
    """Create and configure the CLI argument parser.

    :returns: Configured argument parser.
    :rtype: argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser(description="Huffman-based archiver for multiple files/directories")
    subparsers = parser.add_subparsers(title="subcommands", dest="cmd", required=True)

    archive = subparsers.add_parser("archive", aliases=["a"], help="Archive and compress files/directories")
    archive.add_argument("target", nargs="+", help="Files or directories to archive (recursively)")
    archive.add_argument("-o", "--output", required=True, help="Output archive file path")

    unarchive = subparsers.add_parser("unarchive", aliases=["u"], help="Decompress and unarchive data")
    unarchive.add_argument("archive", help="Archive file to extract")
    unarchive.add_argument("-o", "--output", default=".", help="Destination directory (default: current)")

    return parser


def _iter_entries(targets: List[str]) -> List[Tuple[str, str, bool]]:
    """Build a list of entries for files and directories to include in the archive.

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
                rel_root = '' if rel_root == '.' else rel_root
                for d in dirs:
                    arc_path = os.path.join(base, rel_root, d) if rel_root else os.path.join(base, d)
                    entries.append((_normalize_arc_path(arc_path), os.path.join(root, d), True))
                for f in files:
                    fs_path = os.path.join(root, f)
                    arc_path = os.path.join(base, rel_root, f) if rel_root else os.path.join(base, f)
                    entries.append((_normalize_arc_path(arc_path), fs_path, False))
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
    return path.replace('\\', '/')


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
    normalized = arc_path.replace('/', os.sep).replace('\\', os.sep)
    candidate = os.path.abspath(os.path.join(base_abs, normalized))
    if os.path.commonpath([candidate, base_abs]) != base_abs:
        raise ValueError(f"Unsafe path in archive: {arc_path}")
    return candidate


def create_archive(targets: List[str], output_path: str) -> None:
    """Create an archive file from given targets (files and/or directories).

    Archive format (little-endian):
    - Magic: 'ARH1' (4 bytes)
    - Version: 1 byte
    - Entry count: uint32
    For each entry:
      - Path length: uint32
      - Path (utf-8 bytes)
      - Type: uint8 (0=file, 1=dir)
      - If file:
          - Compressed size: uint32
          - Compressed data bytes (produced by Archiver.compress)

    :param targets: Filesystem targets to include (each file/dir is added recursively).
    :type targets: List[str]
    :param output_path: Destination archive file path.
    :type output_path: str
    :returns: None
    :rtype: None
    :raises FileNotFoundError: If any target does not exist.
    """
    entries = _iter_entries(targets)
    with open(output_path, 'wb') as out:
        out.write(MAGIC)
        out.write(struct.pack('<B', VERSION))
        out.write(struct.pack('<I', len(entries)))

        for arc_path, fs_path, is_dir in entries:
            arc_path_bytes = arc_path.encode('utf-8')
            out.write(struct.pack('<I', len(arc_path_bytes)))
            out.write(arc_path_bytes)
            out.write(struct.pack('<B', 1 if is_dir else 0))
            if not is_dir:
                with open(fs_path, 'rb') as f:
                    data = f.read()
                comp = Archiver().compress(data)
                out.write(struct.pack('<I', len(comp)))
                out.write(comp)


def extract_archive(archive_path: str, dest_dir: str) -> None:
    """Extract an archive created by ``create_archive``.

    :param archive_path: Path to the archive file to extract.
    :type archive_path: str
    :param dest_dir: Destination directory.
    :type dest_dir: str
    :returns: None
    :rtype: None
    :raises ValueError: If the archive header is invalid or uses an unsupported version.
    """
    dest_dir = os.path.abspath(dest_dir)
    os.makedirs(dest_dir, exist_ok=True)
    with open(archive_path, 'rb') as f:
        magic = f.read(4)
        if magic != MAGIC:
            raise ValueError("Invalid archive format (bad magic)")
        ver = struct.unpack('<B', f.read(1))[0]
        if ver != VERSION:
            raise ValueError(f"Unsupported archive version: {ver}")
        count = struct.unpack('<I', f.read(4))[0]

        for _ in range(count):
            plen = struct.unpack('<I', f.read(4))[0]
            pbytes = f.read(plen)
            arc_path = pbytes.decode('utf-8')
            typ = struct.unpack('<B', f.read(1))[0]
            full_path = _safe_join(dest_dir, arc_path)
            if typ == 1:
                os.makedirs(full_path, exist_ok=True)
            else:
                csize = struct.unpack('<I', f.read(4))[0]
                comp = f.read(csize)
                data = Archiver().decompress(comp)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, 'wb') as out:
                    out.write(data)


def main():
    """Entry point for the CLI tool.

    :returns: None
    :rtype: None
    """
    parser = get_parser()
    args = parser.parse_args()

    if args.cmd in ["archive", "a"]:
        create_archive(args.target, args.output)
    elif args.cmd in ["unarchive", "u"]:
        extract_archive(args.archive, args.output)


if __name__ == '__main__':
    main()