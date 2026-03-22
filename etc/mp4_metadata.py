#!/usr/bin/env python3
"""
View and set research-attribution comment metadata in MP4 (or QuickTime .mov) files.
Uses only Python (mutagen); no external OS tools.

Running without set options prints the file's tags.
Use one of --set-research-prohibited, --set-research-credit, or --set-research-anonymous to set the comment.

Shared logic lives in src/app/mp4_metadata_lib.py (used by CLI and lambda-resize).
"""
import argparse
import os
import sys

# Allow importing app when run as script from repo root or etc/
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from app.mp4_metadata_lib import (
    RESEARCH_ANONYMOUS,
    RESEARCH_PROHIBITED,
    get_comment,
    research_credit,
    set_comment,
)


def print_tags(path: str) -> None:
    """Print all tags; emphasize comment if present."""
    try:
        from mutagen.mp4 import MP4

        mp4 = MP4(path)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error opening {path}: {e}", file=sys.stderr)
        sys.exit(1)
    if mp4.tags is None:
        print("(no tags)")
        return
    for key, values in sorted(mp4.tags.items()):
        try:
            key_display = key if isinstance(key, str) and key.isprintable() else repr(key)
        except Exception:  # pylint: disable=broad-exception-caught
            key_display = repr(key)
        for v in values:
            val_str = v if isinstance(v, str) else str(v)
            print(f"{key_display}: {val_str}")
    comment = get_comment(path)
    if comment is not None:
        print(f"\nComment (research/attribution): {comment}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="View or set research-attribution comment in MP4/MOV files (Python only)."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Path to MP4 or MOV file (required unless --help)",
    )
    parser.add_argument(
        "--set-research-prohibited",
        action="store_true",
        help="Set comment to: research use prohibited",
    )
    parser.add_argument(
        "--set-research-credit",
        metavar="NAME",
        default=None,
        help="Set comment to: research use allowed; credit <NAME>",
    )
    parser.add_argument(
        "--set-research-anonymous",
        action="store_true",
        help="Set comment to: research use allowed (no credit required)",
    )
    args = parser.parse_args()

    if args.path is None:
        parser.print_help()
        sys.exit(0)

    path = args.path
    set_opts = [
        args.set_research_prohibited,
        args.set_research_credit is not None,
        args.set_research_anonymous,
    ]
    if sum(set_opts) > 1:
        print("Use only one of --set-research-prohibited, --set-research-credit, --set-research-anonymous.", file=sys.stderr)
        sys.exit(1)

    if args.set_research_prohibited:
        set_comment(path, RESEARCH_PROHIBITED)
        print(f"Set comment: {RESEARCH_PROHIBITED}")
        return
    if args.set_research_credit is not None:
        comment = research_credit(args.set_research_credit)
        set_comment(path, comment)
        print(f"Set comment: {comment}")
        return
    if args.set_research_anonymous:
        set_comment(path, RESEARCH_ANONYMOUS)
        print(f"Set comment: {RESEARCH_ANONYMOUS}")
        return

    print_tags(path)


if __name__ == "__main__":
    main()
