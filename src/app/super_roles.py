"""Atomic super-role management shared by the web application and dbutil."""

import time
import uuid

from botocore.exceptions import ClientError
from pydantic import BaseModel

from . import odb
from .schema import LogEntry

SUPER_ROLE_STATE_EMAIL = "planttracer-system:super-role-state"
SUPERADMIN_USER_IDS = "superadmin_user_ids"
SUPER_ROLE_STATE_VERSION = "super_role_state_version"
SUPER_ROLE_TRANSACTION_RETRIES = 5
GLOBAL_AUDIT_COURSE_ID = "global"

ITEMS = "Items"
LAST_EVALUATED_KEY = "LastEvaluatedKey"


class SuperRoleChange(BaseModel):
    """Result of an idempotent super-role mutation."""

    email: str
    user_id: str
    old_super_role: str
    new_super_role: str
    changed: bool


class SuperRoleState(BaseModel):
    """Versioned singleton used to serialize super-role mutations."""

    version: int
    superadmin_user_ids: list[str]


class ConcurrentSuperRoleChange(RuntimeError):
    """Super-role records kept changing during a mutation."""


class FinalSuperadmin(ValueError):
    """A protected role mutation would remove the final superadmin."""


class UnauthorizedSuperRoleChange(PermissionError):
    """The acting user no longer has superadmin authority."""


def _scan_users(ddbo):
    """Yield every user from a consistent paginated scan."""
    kwargs = {"ConsistentRead": True}
    while True:
        response = ddbo.users.scan(**kwargs)
        yield from response.get(ITEMS, [])
        restart_key = response.get(LAST_EVALUATED_KEY)
        if not restart_key:
            return
        kwargs["ExclusiveStartKey"] = restart_key


def superadmin_user_ids(ddbo=None):
    """Return user ids for current superadmins using a consistent full scan."""
    return {
        user[odb.USER_ID]
        for user in _scan_users(ddbo or odb.DDBO())
        if odb.normalize_super_role(user) == odb.SUPER_ROLE_SUPERADMIN
    }


def read_super_role_state(ddbo):
    """Return the consistent super-role registry, if initialized."""
    item = ddbo.unique_emails.get_item(
        Key={odb.EMAIL: SUPER_ROLE_STATE_EMAIL},
        ConsistentRead=True,
    ).get("Item")
    if item is None:
        return None
    return SuperRoleState(
        version=int(item[SUPER_ROLE_STATE_VERSION]),
        superadmin_user_ids=sorted(item.get(SUPERADMIN_USER_IDS, [])),
    )


def reconcile_super_role_state(ddbo):
    """Synchronize the versioned registry with current user records."""
    for _attempt in range(SUPER_ROLE_TRANSACTION_RETRIES):
        state = read_super_role_state(ddbo)
        actual_ids = sorted(superadmin_user_ids(ddbo))
        if state is None:
            try:
                ddbo.unique_emails.put_item(
                    Item={
                        odb.EMAIL: SUPER_ROLE_STATE_EMAIL,
                        SUPERADMIN_USER_IDS: actual_ids,
                        SUPER_ROLE_STATE_VERSION: 0,
                    },
                    ConditionExpression="attribute_not_exists(#email)",
                    ExpressionAttributeNames={"#email": odb.EMAIL},
                )
                return SuperRoleState(version=0, superadmin_user_ids=actual_ids)
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                    raise
                continue
        if state.superadmin_user_ids == actual_ids:
            return state
        try:
            ddbo.unique_emails.update_item(
                Key={odb.EMAIL: SUPER_ROLE_STATE_EMAIL},
                UpdateExpression="SET #ids = :ids, #version = :next_version",
                ConditionExpression="#ids = :old_ids AND #version = :version",
                ExpressionAttributeNames={
                    "#ids": SUPERADMIN_USER_IDS,
                    "#version": SUPER_ROLE_STATE_VERSION,
                },
                ExpressionAttributeValues={
                    ":ids": actual_ids,
                    ":old_ids": state.superadmin_user_ids,
                    ":version": state.version,
                    ":next_version": state.version + 1,
                },
            )
            return SuperRoleState(
                version=state.version + 1,
                superadmin_user_ids=actual_ids,
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
    raise ConcurrentSuperRoleChange("could not synchronize super-role state")


def _stored_role_condition(user):
    """Return a condition that rejects a concurrent role change."""
    names = {"#role": odb.SUPER_ROLE}
    if odb.SUPER_ROLE in user:
        condition = "#role = :old_role"
        values = {":old_role": user[odb.SUPER_ROLE]}
    else:
        condition = "attribute_not_exists(#role)"
        values = {}
    for suffix, field in (
        ("admin", odb.LEGACY_SUPER_ROLE_ADMIN),
        ("auditor", odb.LEGACY_SUPER_ROLE_AUDITOR),
    ):
        if field in user:
            condition += f" AND #legacy_{suffix}=:legacy_{suffix}"
            names[f"#legacy_{suffix}"] = field
            values[f":legacy_{suffix}"] = user[field]
        else:
            condition += f" AND attribute_not_exists(#legacy_{suffix})"
            names[f"#legacy_{suffix}"] = field
    return condition, names, values


def _audit_transaction(ddbo, *, actor_user_id, target_user_id,
                       old_role, new_role, ipaddr):
    """Build an attributed audit write for a browser role mutation."""
    if actor_user_id is None:
        return None
    event = LogEntry(
        log_id=f"{int(time.time() * 1000)}-{uuid.uuid4()}",
        ipaddr=ipaddr or "unknown",
        user_id=actor_user_id,
        course_id=GLOBAL_AUDIT_COURSE_ID,
        time_t=int(time.time()),
        event_type=f"user.{new_role if new_role != odb.SUPER_ROLE_NONE else old_role}."
                   f"{'removed' if new_role == odb.SUPER_ROLE_NONE else 'assigned'}",
        movie_id="",
        target_user_id=target_user_id,
        old_super_role=old_role,
        new_super_role=new_role,
    ).model_dump(exclude_none=True)
    return {
        "Put": {
            "TableName": ddbo.logs.name,
            "Item": event,
            "ConditionExpression": "attribute_not_exists(#log_id)",
            "ExpressionAttributeNames": {"#log_id": odb.LOG_ID},
        },
    }


def transact_super_role_change(ddbo, user, state, new_role, *,
                               actor_user=None, ipaddr="system"):
    """Atomically update one user role, registry, and optional audit event."""
    user_id = user[odb.USER_ID]
    old_role = odb.normalize_super_role(user)
    new_superadmin_ids = set(state.superadmin_user_ids)
    if old_role == odb.SUPER_ROLE_SUPERADMIN:
        new_superadmin_ids.discard(user_id)
    if new_role == odb.SUPER_ROLE_SUPERADMIN:
        new_superadmin_ids.add(user_id)
    if old_role == odb.SUPER_ROLE_SUPERADMIN and not new_superadmin_ids:
        raise FinalSuperadmin("cannot remove the last superadmin")

    user_condition, user_names, user_values = _stored_role_condition(user)
    user_values[":new_role"] = new_role
    transaction = [
        {
            "Update": {
                "TableName": ddbo.unique_emails.name,
                "Key": {odb.EMAIL: SUPER_ROLE_STATE_EMAIL},
                "UpdateExpression": "SET #ids = :new_ids, #version = :next_version",
                "ConditionExpression": "#ids = :old_ids AND #version = :version",
                "ExpressionAttributeNames": {
                    "#ids": SUPERADMIN_USER_IDS,
                    "#version": SUPER_ROLE_STATE_VERSION,
                },
                "ExpressionAttributeValues": {
                    ":new_ids": sorted(new_superadmin_ids),
                    ":old_ids": state.superadmin_user_ids,
                    ":version": state.version,
                    ":next_version": state.version + 1,
                },
            },
        },
        {
            "Update": {
                "TableName": ddbo.users.name,
                "Key": {odb.USER_ID: user_id},
                "UpdateExpression": "SET #role = :new_role",
                "ConditionExpression": user_condition,
                "ExpressionAttributeNames": user_names,
                "ExpressionAttributeValues": user_values,
            },
        },
    ]
    actor_user_id = None if actor_user is None else actor_user[odb.USER_ID]
    if actor_user is not None and actor_user_id != user_id:
        actor_condition, actor_names, actor_values = _stored_role_condition(actor_user)
        transaction.append({
            "ConditionCheck": {
                "TableName": ddbo.users.name,
                "Key": {odb.USER_ID: actor_user_id},
                "ConditionExpression": actor_condition,
                "ExpressionAttributeNames": actor_names,
                "ExpressionAttributeValues": actor_values,
            },
        })
    audit = _audit_transaction(
        ddbo,
        actor_user_id=actor_user_id,
        target_user_id=user_id,
        old_role=old_role,
        new_role=new_role,
        ipaddr=ipaddr,
    )
    if audit is not None:
        transaction.append(audit)

    try:
        ddbo.dynamodb.meta.client.transact_write_items(
            TransactItems=transaction,
            ClientRequestToken=uuid.uuid4().hex,
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "TransactionCanceledException":
            raise ConcurrentSuperRoleChange("super role changed concurrently") from exc
        raise


def validate_super_role(role):
    """Validate and return a canonical super role."""
    if role not in odb.SUPER_ROLES:
        raise ValueError("super role must be one of: " + ", ".join(sorted(odb.SUPER_ROLES)))
    return role


def set_super_role(user_id, role, *, expected_old_role=None,
                   mismatch_is_noop=False, actor_user_id=None, ipaddr="system"):
    """Set a user's role with last-superadmin and concurrent-actor protection."""
    new_role = validate_super_role(role)
    ddbo = odb.DDBO()
    for _attempt in range(SUPER_ROLE_TRANSACTION_RETRIES):
        state = reconcile_super_role_state(ddbo)
        user = ddbo.get_user(user_id)
        old_role = odb.normalize_super_role(user)
        actor_user = None
        if actor_user_id is not None:
            actor_user = ddbo.get_user(actor_user_id)
            if odb.normalize_super_role(actor_user) != odb.SUPER_ROLE_SUPERADMIN:
                raise UnauthorizedSuperRoleChange(actor_user_id)
        if expected_old_role is not None and old_role != expected_old_role:
            if mismatch_is_noop:
                return SuperRoleChange(
                    email=user[odb.EMAIL], user_id=user_id,
                    old_super_role=old_role, new_super_role=old_role, changed=False,
                )
            raise ValueError(f"user currently has {old_role}, not {expected_old_role}")
        if old_role == new_role:
            return SuperRoleChange(
                email=user[odb.EMAIL], user_id=user_id,
                old_super_role=old_role, new_super_role=new_role, changed=False,
            )
        try:
            transact_super_role_change(
                ddbo, user, state, new_role,
                actor_user=actor_user, ipaddr=ipaddr,
            )
        except ConcurrentSuperRoleChange:
            continue
        return SuperRoleChange(
            email=user[odb.EMAIL], user_id=user_id,
            old_super_role=old_role, new_super_role=new_role, changed=True,
        )
    raise ConcurrentSuperRoleChange("super role kept changing; retry the request")


def set_super_role_by_email(email, role, *, expected_old_role=None):
    """Set a user's canonical super role by email for operator commands."""
    user = odb.DDBO().get_user_email(email)
    return set_super_role(
        user[odb.USER_ID], role, expected_old_role=expected_old_role,
    )
