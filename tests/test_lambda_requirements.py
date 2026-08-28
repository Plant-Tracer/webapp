"""
Ensure Lambda deployment will have runtime dependencies needed by lambda-resize.

The Lambda is built from lambda-resize/src/requirements.txt (generated from only
the lambda dependency group). Tracer code imports cv2 (opencv-python-headless).
If that package is missing from the export, the deployed Lambda fails at runtime
with "No module named 'cv2'".

This test fails if requirements.txt does not list opencv-python-headless, so that
make check catches the problem before deploy.
"""

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_PATH = ROOT / "lambda-resize" / "src" / "requirements.txt"
REQUIRED_PACKAGES = {"imageio-ffmpeg", "mutagen", "opencv-python-headless", "pydantic"}
FORBIDDEN_PACKAGES = {
    "apig-wsgi",
    "aws-lambda-powertools",
    "boto3",
    "botocore",
    "flask",
    "imageio",
    "pillow",
    "requests",
    "urllib3",
}


def requirement_names(content: str) -> set[str]:
    """Return normalized distribution names from an exported requirements file."""
    names = set()
    for line in content.splitlines():
        match = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", line)
        if match:
            names.add(re.sub(r"[-_.]+", "-", match.group(1)).lower())
    return names


def test_lambda_requirements_include_tracer_deps():
    """Lambda requirements.txt must include opencv (cv2) for tracer/trace-movie."""
    subprocess.run(
        ["make", "lambda-resize/src/requirements.txt"], cwd=ROOT, check=True
    )
    packages = requirement_names(REQUIREMENTS_PATH.read_text(encoding="utf-8"))
    assert REQUIRED_PACKAGES <= packages, (
        f"lambda-resize/src/requirements.txt is missing {REQUIRED_PACKAGES - packages}. "
        "Run: uv export --locked --only-group lambda --no-emit-project "
        "--no-hashes --output-file lambda-resize/src/requirements.txt"
    )
    assert not FORBIDDEN_PACKAGES & packages, (
        "lambda-resize/src/requirements.txt contains forbidden packages "
        f"{FORBIDDEN_PACKAGES & packages}"
    )
