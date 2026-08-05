"""Read-only admin API routes."""

from flask import Blueprint, jsonify, request

from . import admin_service, odb
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


@admin_api_bp.get("/movies/<movie_id>/media")
def api_admin_movie_media(movie_id):
    """Return fresh signed play/download URLs for one admin-visible movie."""
    try:
        viewer_user = get_user_dict()
        response = admin_service.admin_movie_media(
            viewer_user=viewer_user,
            movie_id=movie_id,
        )
    except InvalidAPI_Key:
        return jsonify({"error": True, "message": "Invalid api_key"}), 403
    except (admin_service.AdminReadDenied, odb.UnauthorizedUser):
        return jsonify({"error": True, "message": "Admin read access required"}), 403
    except odb.InvalidMovie_Id:
        return jsonify({"error": True, "message": "Movie not found"}), 404
    except ValueError as exc:
        return jsonify({"error": True, "message": str(exc)}), 409
    return jsonify(response.model_dump())
