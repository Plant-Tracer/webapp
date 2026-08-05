"""Command-line entry point for portable analysis-MP4 player bundles."""

import argparse
from pathlib import Path

from .analysis_mp4 import AnalysisMp4Options, create_analysis_bundle


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_mp4", help="source MP4 path")
    parser.add_argument("output_dir", help="new output bundle directory")
    parser.add_argument("--rotation", type=int, default=0, choices=(0, 90, 180, 270))
    parser.add_argument("--max-width", type=int, default=640)
    parser.add_argument("--max-height", type=int, default=480)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Create a portable analysis-MP4 player bundle and report its metadata."""
    args = build_parser().parse_args(argv)
    options = AnalysisMp4Options(
        rotation=args.rotation,
        max_width=args.max_width,
        max_height=args.max_height,
    )
    result = create_analysis_bundle(
        source_path=Path(args.input_mp4),
        output_dir=Path(args.output_dir),
        options=options,
    )
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
