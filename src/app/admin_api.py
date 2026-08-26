"""Admin API routes."""

import smtplib

from flask import Blueprint, jsonify, request
from pydantic import ValidationError
from validate_email_address import validate_email

from . import admin_service, course_management, mailer, odb, super_roles
from .apikey import get_user_dict
from .constants import logger
from .odb import InvalidAPI_Key

admin_api_bp = Blueprint("admin_api", __name__)


def _admin_user_summary(user, viewer_user):
    """Return a target user limited to the acting administrator's scope."""
    access = odb.admin_read_access(viewer_user)
    visible_course_ids = None if access.all_courses else set(access.course_ids)
    return admin_service.user_summary(user, visible_course_ids=visible_course_ids)


def _change_course_administrator(course_id, *, assigned, user_id=None,
                                 email_payload=None):
    """Apply one authorized course-administrator mutation."""
    try:
        viewer_user = get_user_dict()
        if not odb.can_manage_course_administrators(viewer_user, course_id):
            return jsonify({
                "error": True,
                "message": "Course administrator access required",
            }), 403
        if email_payload is not None:
            email_request = admin_service.AdminCourseAdministratorRequest.model_validate(
                email_payload
            )
            if not validate_email(email_request.email, check_mx=False):
                return jsonify({
                    "error": True,
                    "message": "Administrator email is invalid",
                }), 400
            target_user = odb.get_user_email(email_request.email)
            user_id = target_user[odb.USER_ID]
        if not odb.is_user_id(user_id) or not course_id:
            return jsonify({
                "error": True,
                "message": "Invalid course-administrator identifier",
            }), 400
        if assigned:
            change = odb.add_course_admin(
                admin_id=user_id,
                course_id=course_id,
                actor_user_id=viewer_user[odb.USER_ID],
                ipaddr=request.remote_addr,
                authorize_actor=True,
            )
        else:
            change = odb.remove_course_admin(
                admin_id=user_id,
                course_id=course_id,
                actor_user_id=viewer_user[odb.USER_ID],
                ipaddr=request.remote_addr,
                protect_last_admin=True,
                authorize_actor=True,
            )
        target_user = odb.get_user(user_id)
        response = admin_service.AdminCourseAdministratorChange(
            course_id=course_id,
            administrator=_admin_user_summary(target_user, viewer_user),
            assigned=change.assigned,
            changed=change.changed,
        )
    except InvalidAPI_Key:
        return jsonify({"error": True, "message": "Invalid api_key"}), 403
    except ValidationError:
        return jsonify({
            "error": True,
            "message": "Invalid administrator assignment request",
        }), 400
    except (odb.InvalidUser_Id, odb.InvalidUser_Email):
        return jsonify({"error": True, "message": "User not found"}), 404
    except odb.InvalidCourse_Id:
        return jsonify({"error": True, "message": "Course not found"}), 404
    except odb.DisabledCourseAdmin:
        return jsonify({"error": True, "message": "Administrator account is disabled"}), 409
    except odb.FinalCourseAdmin:
        return jsonify({
            "error": True,
            "message": "A course must retain at least one administrator",
        }), 409
    except odb.CourseAdminConflict:
        return jsonify({
            "error": True,
            "message": "Administrator assignments changed concurrently; retry the request",
        }), 409
    except odb.UnauthorizedCourseAdminChange:
        return jsonify({
            "error": True,
            "message": "Course administrator access required",
        }), 403
    return jsonify(response.model_dump())


def _change_superadmin(user_id, *, assigned):
    """Grant or revoke superadmin with atomic final-role protection."""
    try:
        viewer_user = get_user_dict()
        if odb.normalize_super_role(viewer_user) != odb.SUPER_ROLE_SUPERADMIN:
            return jsonify({"error": True, "message": "Superadmin access required"}), 403
        if not odb.is_user_id(user_id):
            return jsonify({
                "error": True,
                "message": "Invalid user identifier",
            }), 400
        change = super_roles.set_super_role(
            user_id,
            odb.SUPER_ROLE_SUPERADMIN if assigned else odb.SUPER_ROLE_NONE,
            expected_old_role=None if assigned else odb.SUPER_ROLE_SUPERADMIN,
            mismatch_is_noop=not assigned,
            actor_user_id=viewer_user[odb.USER_ID],
            ipaddr=request.remote_addr,
        )
        target_user = odb.get_user(user_id)
        response = admin_service.AdminSuperadminChange(
            user=admin_service.user_summary(target_user),
            old_super_role=change.old_super_role,
            new_super_role=change.new_super_role,
            changed=change.changed,
        )
    except InvalidAPI_Key:
        return jsonify({"error": True, "message": "Invalid api_key"}), 403
    except odb.InvalidUser_Id:
        return jsonify({"error": True, "message": "User not found"}), 404
    except super_roles.FinalSuperadmin:
        return jsonify({
            "error": True,
            "message": "The final superadmin cannot be removed",
        }), 409
    except super_roles.UnauthorizedSuperRoleChange:
        return jsonify({"error": True, "message": "Superadmin access required"}), 403
    except super_roles.ConcurrentSuperRoleChange:
        return jsonify({
            "error": True,
            "message": "Superadmin assignments changed concurrently; retry the request",
        }), 409
    return jsonify(response.model_dump())


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


@admin_api_bp.put("/courses/<course_id>/administrators/<user_id>")
def api_admin_assign_course_administrator(course_id, user_id):
    """Assign an existing user as a course administrator."""
    return _change_course_administrator(course_id, assigned=True, user_id=user_id)


@admin_api_bp.put("/courses/<course_id>/administrators")
def api_admin_assign_course_administrator_by_email(course_id):
    """Assign an exact registered email as a course administrator."""
    return _change_course_administrator(
        course_id,
        assigned=True,
        email_payload=request.get_json(silent=True) or {},
    )


@admin_api_bp.delete("/courses/<course_id>/administrators/<user_id>")
def api_admin_remove_course_administrator(course_id, user_id):
    """Remove course-admin status while retaining course membership."""
    return _change_course_administrator(course_id, assigned=False, user_id=user_id)


@admin_api_bp.put("/users/<user_id>/superadmin")
def api_admin_assign_superadmin(user_id):
    """Grant superadmin to an existing registered user."""
    return _change_superadmin(user_id, assigned=True)


@admin_api_bp.delete("/users/<user_id>/superadmin")
def api_admin_remove_superadmin(user_id):
    """Remove superadmin while protecting the final assignment."""
    return _change_superadmin(user_id, assigned=False)


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
