"""
Maintain the DynamoDB Database.
"""

#pylint: disable=invalid-name

import copy
import json
import os
import os.path
import time
from collections.abc import Callable

import boto3
from tabulate import tabulate
from botocore.exceptions import ClientError


from . import odb
from .s3_presigned import s3_client
from .odb import USER_ID,DDBO
from .constants import C,logger
from .paths import ROOT_DIR

KeySchema = 'KeySchema'
KeyType = 'KeyType'
TableName = 'TableName'
AttributeName = 'AttributeName'
AttributeType = 'AttributeType'
AttributeDefinitions = 'AttributeDefinitions'
GlobalSecondaryIndexes = 'GlobalSecondaryIndexes'
IndexName = 'IndexName'
BillingMode = 'BillingMode'
PAY_PER_REQUEST = 'PAY_PER_REQUEST'
HASH = 'HASH'
RANGE = 'RANGE'
COMMENT = 'Comment'
S = 'S' # string
N = 'N' # number

SCHEMA_VERSION = 'schema_version'
TABLES = 'tables'
TABLE_DEFINITION_SCHEMA_VERSION = 1
TABLE_DEFINITION_FILE = os.path.join(ROOT_DIR, 'etc', 'dynamodb_tables.json')


def load_table_configurations(definition_path=TABLE_DEFINITION_FILE):
    """Return DynamoDB create_table configurations from the JSON table definition."""
    with open(definition_path, encoding='utf-8') as json_file:
        definition = json.load(json_file)
    try:
        schema_version = definition[SCHEMA_VERSION]
        table_configurations = definition[TABLES]
    except KeyError as e:
        raise ValueError(f"{definition_path} is missing required key {e}") from e
    if schema_version != TABLE_DEFINITION_SCHEMA_VERSION:
        raise ValueError(
            f"{definition_path} schema_version {schema_version} is not supported; "
            f"expected {TABLE_DEFINITION_SCHEMA_VERSION}"
        )
    if not isinstance(table_configurations, list):
        raise ValueError(f"{definition_path} key {TABLES} must be a list")
    return copy.deepcopy(table_configurations)


def table_prefix_from_env():
    table_prefix = os.environ.get(C.DYNAMODB_TABLE_PREFIX)
    if table_prefix is None:
        raise RuntimeError(f"Environment variable {C.DYNAMODB_TABLE_PREFIX} must be set")
    return (table_prefix.rstrip('-') + '-') if table_prefix else ''


def create_tables(*, ignore_table_exists=False, status: Callable[[str], None] | None = None):
    """Creates DynamoDB tables based on etc/dynamodb_tables.json.
    Connects to the local DynamoDB instance using AWS_ENDPOINT_URL_DYNAMODB.

    :param ignore_table_exists: Tables to ignore if they already exist
    :param status: Optional callback for user-visible progress messages
    :raises ClientError: If a DynamoDB client-side error occurs (e.g., table already exists).
    :raises Exception: For any unexpected errors during creation.
    :return: the connected ddbo object
    """
    table_prefix = table_prefix_from_env()
    dynamodb = DDBO.resource()
    table_configurations = load_table_configurations()
    table_count = len(table_configurations)
    if status:
        status(
            f"Creating {table_count} DynamoDB tables with prefix '{table_prefix}'. "
            "This usually takes 1-3 minutes in AWS."
        )
        status("Tables are created sequentially; DynamoDB status checks may be 20 seconds apart.")
    for table_number, table_config in enumerate(table_configurations, start=1):
        # prepend the prefix to the table name before creating it
        tc = copy.deepcopy(table_config)
        try:
            del tc[COMMENT]     # remove comment if present
        except KeyError:
            pass
        tc[TableName] = table_name = table_prefix + tc[TableName]
        try:
            if status:
                status(f"[{table_number}/{table_count}] Creating {table_name}...")
            table = dynamodb.create_table(**tc)
            # because tables don't get created instantly and wait_until_exists
            # has a hard-coded 20-second delay, we sleep a bit...
            time.sleep(C.TABLE_CREATE_SLEEP_TIME)
            if status:
                status(f"[{table_number}/{table_count}] Waiting for {table_name} to become ACTIVE...")
            logger.info("Waiting for table %s to be active...", table_name)
            table.wait_until_exists()
            if status:
                status(f"[{table_number}/{table_count}] Ready: {table_name}")
            logger.info("Table %s created successfully!", table_name)
        except ClientError as e:
            if e.response['Error']['Code'] in ('TableAlreadyExistsException','ResourceInUseException'):
                # ignore_table_exists can be a bool or a collection of table names to ignore
                should_warn = not ignore_table_exists
                if isinstance(ignore_table_exists, (list, tuple, set)) and table_name in ignore_table_exists:
                    should_warn = False
                if status:
                    status(f"[{table_number}/{table_count}] Already exists: {table_name}")
                if should_warn:
                    logger.warning("Table %s already exists.", table_name)
            else:
                logger.error("Error creating table %s: %s.  endpoint=%s", table_name, e, dynamodb.meta.client.meta.endpoint_url)


def drop_dynamodb_table(dynamodb, table_name: str, silent_warnings=False):
    """Drops a specified DynamoDB table from the local instance.

    :param table_name: The name of the table to drop.
    :type table_name: str
    :param dynamodb_resource: The boto3 DynamoDB resource object.
    :type dynamodb_resource: boto3.resources.base.ServiceResource
    :raises ClientError: If a DynamoDB client-side error occurs (e.g., table not found).
    :raises Exception: For any unexpected errors during deletion.
    """
    logger.info("Attempting to delete table: %s", table_name)
    try:
        table = dynamodb.Table(table_name)
        table.delete() # Initiates the deletion process
        table.wait_until_not_exists()
        logger.info("Table %s deleted successfully!", table_name)

    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            if not silent_warnings:
                logger.warning("Table %s does not exist when dropping table.", table_name)
        elif e.response['Error']['Code'] == 'ValidationException' and "table is being deleted" in str(e):
            if not silent_warnings:
                logger.warning("Table %s is already in the process of being deleted.", table_name)
        else:
            logger.error("Error deleting table %s: %s", table_name, e)


def drop_tables(silent_warnings=False):
    table_prefix = table_prefix_from_env()
    dynamodb = DDBO.resource()
    tables_to_drop = [ table_prefix + config[TableName] for config in load_table_configurations() ]
    for table_name in tables_to_drop:
        drop_dynamodb_table(dynamodb, table_name, silent_warnings=silent_warnings)

def purge_all_movies(ddbo):
    """"Deleting an entire table is significantly more efficient than removing items one-by-one,
    which essentially doubles the write throughput as you do as many delete operations as put operations.
    This does not delete the movie files.
    """
    ddbo.dynamodb.meta.client.delete_table(TableName = ddbo.table_prefix + 'movies')
    create_tables(ignore_table_exists={ddbo.table_prefix + 'movies'})

#pylint: disable=too-many-arguments
def create_course(*, course_id, course_key, course_name, admin_email,
                  admin_name,max_enrollment=C.DEFAULT_MAX_ENROLLMENT,
                  ok_if_exists = False ):
    """
    :param course_id: course to be created
    :param course_key: course key for student registrations
    :param course_name: course name
    :param admin_email: Email address for the first course admin. User is automatically created if necessary.
    :param admin_name: Admin's name
    :param max_enrollment: Maximum enrollment
    """
    odb.create_course(course_id = course_id,
                      course_key = course_key,
                      course_name = course_name,
                      max_enrollment = max_enrollment,
                      ok_if_exists = ok_if_exists)

    # set up the admin; register_email returns {USER_ID: ...}, so we can avoid an
    # immediate read by email (and any read-after-write inconsistency).
    admin_result = odb.register_email(email=admin_email, course_id=course_id, user_name=admin_name)
    admin_id = admin_result[USER_ID]
    odb.add_course_admin(admin_id=admin_id, course_id=course_id)
    logger.info("generated course_key=%s  admin_email=%s admin_id=%s",course_key,admin_email,admin_id)


def delete_course(*, course_id):
    """Delete the course"""
    logger.debug("delete_course(%s)",course_id)
    course = odb.lookup_course_by_id(course_id=course_id)
    if not course:
        raise ValueError(f"course {course_id} does not exist")
    odb.delete_course(course_id=course_id)

def count_table_items(table, **kwargs):
    logger.warning("scan table %s",table)
    total = 0
    response = table.scan(Select='COUNT', **kwargs)
    total += response['Count']
    while 'LastEvaluatedKey' in response:
        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'], Select='COUNT', **kwargs)
        total += response['Count']
    return total

def report(ddbo):
    headers = ['table','.item_count','count_table_items()']
    rows = []
    for table in ddbo.tables:
        rows.append([table.name,table.item_count, count_table_items(table)])
    print(tabulate(rows,headers=headers))


def _flush_delete_batch(bucket: str, objects: list) -> None:
    """
    Helper to delete up to 1000 objects at once.
    """
    s3 = s3_client()
    try:
        resp = s3.delete_objects(Bucket=bucket, Delete={'Objects': objects})
        deleted = resp.get('Deleted', [])
        errors = resp.get('Errors', [])
        logger.info("deleted %s objects from %s", len(deleted), bucket)
        for err in errors:
            logger.error("failed to delete %s: %s", err['Key'], err['Message'])
    except ClientError as e:
        logger.error("batch delete failed for bucket %s: %s", bucket, e.response['Error']['Message'])

def purge_test_obects(bucket: str):
    """
    Delete all objects in `bucket` whose keys start with 'test-'.
    This covers prefixes like 'test-1/', 'test-foo/', etc.
    """
    s3_prefix = "test-"
    logger.info("deleting objects in bucket %s with S3 prefix %s", bucket, s3_prefix)

    s3 = s3_client()
    paginator = s3.get_paginator('list_objects_v2')
    to_delete = []

    for page in paginator.paginate(Bucket=bucket, Prefix=s3_prefix):
        for obj in page.get('Contents', []):
            to_delete.append({'Key': obj['Key']})
            if len(to_delete) == 1000:
                _flush_delete_batch(bucket, to_delete)
                to_delete.clear()

    if to_delete:
        _flush_delete_batch(bucket, to_delete)


def purge_test_tables(region_name=None):
    """
    Delete all S3 objects that start with test-*/
    Delete all DynamoDB tables whose names start with 'test-'.
    """
    session_kwargs = {}
    session = boto3.Session(**session_kwargs)
    client = session.client('dynamodb', region_name=region_name)

    paginator = client.get_paginator('list_tables')
    tables_to_delete = []

    # Collect all table names beginning with 'test-'
    for page in paginator.paginate():
        for name in page.get('TableNames', []):
            if name.startswith('test-'):
                tables_to_delete.append(name)

    if not tables_to_delete:
        logger.info("No tables found with prefix 'test-'.")
        return

    logger.info("tables to delete: %s:",len(tables_to_delete))
    for name in tables_to_delete:
        print("  -", name)

    # Delete each table and wait for its deletion
    for name in tables_to_delete:
        try:
            logger.info("Deleting table %s",name)
            client.delete_table(TableName=name)
            waiter = client.get_waiter('table_not_exists')
            waiter.wait(TableName=name)
        except ClientError as e:
            logger.error("Error deleting %s: %s",name,e.response['Error']['Message'])
            raise
