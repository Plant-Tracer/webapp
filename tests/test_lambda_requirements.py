"""
Ensure Lambda deployment will have runtime dependencies needed by lambda-resize.

The Lambda is built from lambda-resize/src/requirements.txt (generated from only
the lambda dependency group). Tracer code imports cv2 (opencv-python-headless).
If that package is missing from the export, the deployed Lambda fails at runtime
with "No module named 'cv2'".

This test fails if requirements.txt does not list opencv-python-headless, so that
make check catches the problem before deploy.
"""

import os
import subprocess
from pathlib import Path
import pytest



REQUIREMENTS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "lambda-resize", "src", "requirements.txt"
)
REQUIRED_PACKAGES = ["imageio-ffmpeg", "mutagen", "opencv-python-headless", "pydantic"]
FORBIDDEN_PACKAGES = [
    "apig-wsgi",
    "aws-lambda-powertools",
    "boto3",
    "botocore",
    "flask",
    "imageio==",
    "pillow",
    "requests",
    "urllib3",
]


def test_lambda_requirements_include_tracer_deps():
    """Lambda requirements.txt must include opencv (cv2) for tracer/trace-movie."""
    cmd = f"cd {Path(__file__).parent.parent} ; make lambda-resize/src/requirements.txt"
    subprocess.call(cmd,shell=True)
    if not os.path.isfile(REQUIREMENTS_PATH):
        pytest.skip(f"Lambda requirements not found: {REQUIREMENTS_PATH}")
    with open(REQUIREMENTS_PATH, encoding="utf-8") as f:
        content = f.read()
    for pkg in REQUIRED_PACKAGES:
        assert pkg in content, (
            f"lambda-resize/src/requirements.txt must contain '{pkg}' "
            "(needed by tracer.py / trace-movie). "
            "Run: poetry export --only lambda --format=requirements.txt "
            "--output lambda-resize/src/requirements.txt --without-hashes"
        )
    normalized_content = content.lower()
    for pkg in FORBIDDEN_PACKAGES:
        assert pkg not in normalized_content, (
            f"lambda-resize/src/requirements.txt must not contain '{pkg}'"
        )
