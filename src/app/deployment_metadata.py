"""Read deploy-time metadata embedded in a Lambda artifact."""

import logging
import os
from pathlib import Path

from pydantic import BaseModel, ValidationError

DEPLOYED_AT_ENV = "PLANTTRACER_DEPLOYED_AT"
DEPLOY_METADATA_FILENAME = "deploy_metadata.json"
UNKNOWN_DEPLOYED_AT = "unknown"

logger = logging.getLogger(__name__)


class DeployMetadata(BaseModel):
    """Metadata stamped into the packaged Lambda application."""

    deployed_at: str = ""


def deployed_at(metadata_path: Path | None = None) -> str:
    """Return the package deploy time, with an environment override for local runs."""
    deployed_at_value = os.environ.get(DEPLOYED_AT_ENV, "").strip()
    if metadata_path is None:
        metadata_path = Path(__file__).with_name(DEPLOY_METADATA_FILENAME)
    if metadata_path.exists():
        try:
            metadata = DeployMetadata.model_validate_json(
                metadata_path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, ValidationError, ValueError):
            logger.warning("could not read deploy metadata from %s", metadata_path)
        else:
            deployed_at_value = metadata.deployed_at.strip() or deployed_at_value
    return deployed_at_value or UNKNOWN_DEPLOYED_AT
