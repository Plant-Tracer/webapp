"""Read-only admin API routes."""

from flask import Blueprint, jsonify, request

from . import admin_service
from .apikey import get_user_dict
from .odb import InvalidAPI_Key

admin_api_bp = Blueprint("admin_api", __name__)


@admin_api_bp.get("/summary")
def api_admin_summary():
    """Return the read-only admin landing-page summary."""
    try:
        viewer_user = get_user_dict()
        response = admin_service.admin_summary(
            viewer_user=viewer_user,
            course_marker=request.args.get("course_marker"),
            user_marker=request.args.get("user_marker"),
            movie_marker=request.args.get("movie_marker"),
            limit=request.args.get("limit"),
            section=request.args.get("section"),
        )
    except InvalidAPI_Key:
        return jsonify({"error": True, "message": "Invalid api_key"}), 403
    except admin_service.AdminReadDenied:
        return jsonify({"error": True, "message": "Admin read access required"}), 403
    except admin_service.InvalidRestartMarker as exc:
        return jsonify({"error": True, "message": str(exc)}), 400
    except admin_service.InvalidAdminSection as exc:
        return jsonify({"error": True, "message": str(exc)}), 400
    return jsonify(response.model_dump())
