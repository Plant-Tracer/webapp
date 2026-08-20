"""Admin API routes."""

import smtplib

from flask import Blueprint, jsonify, request
from pydantic import ValidationError
from validate_email_address import validate_email

from . import admin_service, course_management, mailer, odb
from .apikey import get_user_dict
from .constants import logger
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


@admin_api_bp.post("/courses")
def api_admin_create_course():
    """Create a course and its initial administrator as a superadmin."""
    try:
        viewer_user = get_user_dict()
        if odb.normalize_super_role(viewer_user) != odb.SUPER_ROLE_SUPERADMIN:
            return jsonify({"error": True, "message": "Superadmin access required"}), 403
        change = admin_service.AdminCourseCreateRequest.model_validate(
            request.get_json(silent=True) or {}
        )
        admin_email = odb.normalize_email(change.admin_email)
        if not validate_email(admin_email, check_mx=False):
            return jsonify({"error": True, "message": "Administrator email is invalid"}), 400
        admin_already_assigned = False
        try:
            existing_user = odb.get_user_email(admin_email)
            if not existing_user.get(odb.ENABLED):
                return jsonify({
                    "error": True,
                    "message": "Administrator account is disabled",
                }), 409
            admin_name = existing_user.get(odb.USER_NAME)
            if not isinstance(admin_name, str) or not admin_name.strip():
                return jsonify({
                    "error": True,
                    "message": "Administrator account has no name",
                }), 409
            admin_already_assigned = change.course_id in existing_user.get(
                odb.ADMIN_FOR_COURSES, []
            )
        except odb.InvalidUser_Email:
            admin_name = change.admin_name

        result = course_management.create_course_with_admin(
            course_id=change.course_id,
            course_name=change.course_name,
            admin_email=admin_email,
            admin_name=admin_name,
            send_email=False,
        )
        if result.created or not admin_already_assigned:
            odb.DDBO().put_admin_log(
                event_type="course.created" if result.created else "course.admin.assigned",
                actor_user_id=viewer_user[odb.USER_ID],
                target_user_id=result.admin_user.user_id,
                course_id=result.course.course_id,
                ipaddr=request.remote_addr,
            )
    except InvalidAPI_Key:
        return jsonify({"error": True, "message": "Invalid api_key"}), 403
    except ValidationError:
        return jsonify({"error": True, "message": "Invalid course creation request"}), 400
    except odb.ExistingCourse_Id:
        return jsonify({
            "error": True,
            "message": "Course identifier or registration key is already in use",
        }), 409
    except course_management.CourseNameConflict:
        return jsonify({
            "error": True,
            "message": "Course ID conflicts with an existing course name",
        }), 409

    email_sent = True
    message = "Course created and administrator email sent"
    try:
        course_management.send_course_created_notification(
            course=result.course,
            admin_user=result.admin_user,
            planttracer_endpoint=request.url_root.rstrip("/"),
        )
    except (mailer.InvalidMailerConfiguration, mailer.NoMailerConfiguration,
            smtplib.SMTPException, OSError) as exc:
        logger.warning("course %s created but administrator email failed: %s",
                       result.course.course_id, exc)
        email_sent = False
        message = "Course created, but the administrator email could not be sent"

    response = admin_service.AdminCourseCreateResponse(
        course=result.course,
        administrator=admin_service.AdminCourseAdministrator(
            user_id=result.admin_user.user_id,
            email=result.admin_user.email,
            user_name=result.admin_user.user_name,
        ),
        created=result.created,
        email_sent=email_sent,
        message=message if result.created else message.replace("created", "updated", 1),
    )
    return jsonify(response.model_dump()), 201 if result.created else 200


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


@admin_api_bp.get("/movies/<movie_id>/storage-health")
def api_admin_movie_storage_health(movie_id):
    """Return read-only S3 object health for one admin-visible movie."""
    try:
        viewer_user = get_user_dict()
        response = admin_service.admin_movie_storage_health(
            viewer_user=viewer_user,
            movie_id=movie_id,
        )
    except InvalidAPI_Key:
        return jsonify({"error": True, "message": "Invalid api_key"}), 403
    except (admin_service.AdminReadDenied, odb.UnauthorizedUser):
        return jsonify({"error": True, "message": "Admin read access required"}), 403
    except odb.InvalidMovie_Id:
        return jsonify({"error": True, "message": "Movie not found"}), 404
    return jsonify(response.model_dump())
