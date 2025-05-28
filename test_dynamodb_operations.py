# test_dynamodb_operations.py
import pytest
import logging
import uuid

# It's good practice to import the actual boto3 for types, etc.
import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key

# Configure logging for the test module
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


# Helper functions (adapted to rely solely on the dynamodb_resource passed in)
def insert_records(records_data: list, dynamodb_resource: 'boto3.resources.factory.ServiceResource'):
    """Inserts records into DynamoDB tables based on provided data.

    :param records_data: A list of dictionaries, each specifying a table and items to insert.
    :type records_data: list
    :param dynamodb_resource: The boto3 DynamoDB resource object.
    :type dynamodb_resource: boto3.resources.factory.ServiceResource
    :raises ClientError: If a DynamoDB client-side error occurs during item insertion.
    :raises Exception: For any unexpected errors during item insertion.
    """
    logger.info("Starting record insertion...")
    for record_config in records_data:
        table_name = record_config['table_name']
        items = record_config['items']
        table = dynamodb_resource.Table(table_name)
        logger.info("Attempting to insert records into table: %s", table_name)

        for item_data in items:
            item_key_str = "" # Placeholder for logging
            if table_name == 'frames':
                 item_key_str = f"movieId={item_data.get('movieId', 'N/A')}, frameNumber={item_data.get('frameNumber', 'N/A')}"
            else:
                 item_key_str = f"id={item_data.get('id', 'N/A')}"

            try:
                table.put_item(Item=item_data)
                logger.info("Successfully added item to %s: %s", table_name, item_key_str)
            except ClientError as e:
                logger.error("Error adding item to %s (%s): %s",
                             table_name, item_key_str, e)
                raise # Re-raise to fail the test if insert fails
            except Exception as e:
                logger.error("Unexpected error adding item to %s (%s): %s",
                             table_name, item_key_str, e)
                raise # Re-raise to fail the test if insert fails
    logger.info("Record insertion complete.")


def validate_records(validation_data: list, dynamodb_resource: 'boto3.resources.factory.ServiceResource') -> bool:
    """Validates records in DynamoDB tables by attempting to retrieve them.

    This function attempts to fetch specific items based on predefined IDs.

    :param validation_data: A list of dictionaries, each specifying a table and keys for validation.
    :type validation_data: list
    :param dynamodb_resource: The boto3 DynamoDB resource object.
    :type dynamodb_resource: boto3.resources.factory.ServiceResource
    :returns: True if all specified records are found and validated, False otherwise.
    :rtype: bool
    :raises ClientError: If a DynamoDB client-side error occurs during item retrieval.
    :raises Exception: For any unexpected errors during item retrieval.
    """
    logger.info("Starting record validation...")
    all_validated = True

    for config in validation_data:
        table_name = config['table_name']
        key_attribute = config['key_attribute']
        key_value = config['key_value']
        table = dynamodb_resource.Table(table_name)

        item_key_str = f"{key_attribute}={key_value}"

        logger.info("Attempting to retrieve from table: %s (%s)", table_name, item_key_str)

        try:
            if table_name == 'frames':
                response = table.query(
                    KeyConditionExpression=Key(key_attribute).eq(key_value)
                )
                items = response.get('Items', [])
                if items:
                    logger.info("Found %d frames for movie %s in table %s.", len(items), key_value, table_name)
                    # For a real unit test, you might assert count: assert len(items) > 0
                else:
                    logger.warning("No frames found for movie %s in table %s. Validation failed for this entry.", key_value, table_name)
                    all_validated = False
            else:
                response = table.get_item(
                    Key={key_attribute: key_value}
                )
                item = response.get('Item')
                if item:
                    logger.info("Found item in %s (%s): %s", table_name, item_key_str, item)
                    # For a real unit test, you might assert content: assert item.get('some_field') == expected_value
                else:
                    logger.warning("Item not found in %s (%s). Validation failed for this entry.", table_name, item_key_str)
                    all_validated = False

        except ClientError as e:
            logger.error("Error retrieving from table %s (%s): %s",
                         table_name, item_key_str, e)
            all_validated = False
        except Exception as e:
            logger.error("Unexpected error retrieving from table %s (%s): %s",
                         table_name, item_key_str, e)
            all_validated = False
    logger.info("Record validation complete. All records validated: %s", all_validated)
    return all_validated


# --- Pytest Test Function ---

# Pytest automatically discovers functions starting with 'test_'
# It injects fixtures as arguments
def test_insert_and_validate_records(dynamodb_resource, dynamodb_tables):
    """
    Tests the insertion and subsequent validation of records in DynamoDB Local.
    
    This test leverages the `dynamodb_resource` (session-scoped boto3 client) and
    `dynamodb_tables` (function-scoped table setup/teardown) fixtures.
    """
    logger.info("--- Running insert and validate test case... ---")

    # Generate unique IDs for this specific test run
    generated_ids = {
        'user_id': str(uuid.uuid4()),
        'course_id': str(uuid.uuid4()),
        'movie_id': str(uuid.uuid4())
    }

    # Prepare sample records using the generated IDs
    sample_records_for_test = [
        {
            'table_name': 'users',
            'items': [
                {
                    'id': generated_ids['user_id'],
                    'email': 'testuser@example.com',
                    'username': 'pytest_user',
                    'firstName': 'Pytest',
                    'lastName': 'User',
                    'primaryCourseId': generated_ids['course_id']
                }
            ]
        },
        {
            'table_name': 'courses',
            'items': [
                {
                    'id': generated_ids['course_id'],
                    'name': 'Pytest DynamoDB Course',
                    'instructorId': generated_ids['user_id']
                }
            ]
        },
        {
            'table_name': 'movies',
            'items': [
                {
                    'id': generated_ids['movie_id'],
                    'title': 'Pytest Movie',
                    'courseId': generated_ids['course_id'],
                    'userId': generated_ids['user_id'],
                    'isPublished': 1,
                    'isDeleted': 0,
                    'description': 'A movie inserted via pytest.'
                }
            ]
        },
        {
            'table_name': 'frames',
            'items': [
                {
                    'movieId': generated_ids['movie_id'],
                    'frameNumber': 1, # Only one frame for brevity
                    'frameS3Url': f's3://pytest-frame-bucket/{generated_ids["movie_id"]}/frame_0001.jpg',
                    'annotations': [
                        {'x': 10, 'y': 20, 'label': 'pytest_obj_1'}
                    ]
                }
            ]
        }
    ]

    # Prepare validation keys using the generated IDs
    validation_keys_for_test = [
        {
            'table_name': 'users',
            'key_attribute': 'id',
            'key_value': generated_ids['user_id']
        },
        {
            'table_name': 'courses',
            'key_attribute': 'id',
            'key_value': generated_ids['course_id']
        },
        {
            'table_name': 'movies',
            'key_attribute': 'id',
            'key_value': generated_ids['movie_id']
        },
        {
            'table_name': 'frames',
            'key_attribute': 'movieId', # For frames, we query by movieId
            'key_value': generated_ids['movie_id']
        }
    ]

    # Perform insertion
    insert_records(sample_records_for_test, dynamodb_resource)

    # Perform validation and assert the result
    validation_success = validate_records(validation_keys_for_test, dynamodb_resource)
    assert validation_success, "One or more records failed validation."

    logger.info("--- Test case PASSED: All records validated successfully. ---")
