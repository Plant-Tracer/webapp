import logging
import argparse

import boto3
from botocore.exceptions import ClientError

# Configure basic logging
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Global Constants ---
DEFAULT_DYNAMODB_ENDPOINT = 'http://localhost:8010'
DEFAULT_PROVISIONED_THROUGHPUT = {
    'ReadCapacityUnits': 1,
    'WriteCapacityUnits': 1
}

# Define all table configurations as a global constant
TABLE_CONFIGURATIONS = [
    {
        'TableName': 'users',
        'KeySchema': [
            {'AttributeName': 'id', 'KeyType': 'HASH'}
        ],
        'AttributeDefinitions': [
            {'AttributeName': 'id', 'AttributeType': 'S'},
            {'AttributeName': 'email', 'AttributeType': 'S'}
        ],
        'GlobalSecondaryIndexes': [
            {
                'IndexName': 'EmailIndex',
                'KeySchema': [
                    {'AttributeName': 'email', 'KeyType': 'HASH'}
                ],
                'Projection': {
                    'ProjectionType': 'ALL'
                },
                'ProvisionedThroughput': DEFAULT_PROVISIONED_THROUGHPUT
            }
        ],
        'ProvisionedThroughput': DEFAULT_PROVISIONED_THROUGHPUT
    },
    {
        'TableName': 'courses',
        'KeySchema': [
            {'AttributeName': 'id', 'KeyType': 'HASH'}
        ],
        'AttributeDefinitions': [
            {'AttributeName': 'id', 'AttributeType': 'S'}
        ],
        'ProvisionedThroughput': DEFAULT_PROVISIONED_THROUGHPUT
    },
    {
        'TableName': 'movies',
        'KeySchema': [
            {'AttributeName': 'id', 'KeyType': 'HASH'}
        ],
        'AttributeDefinitions': [
            {'AttributeName': 'id', 'AttributeType': 'S'},
            {'AttributeName': 'courseId', 'AttributeType': 'S'},
            {'AttributeName': 'userId', 'AttributeType': 'S'},
            {'AttributeName': 'isPublished', 'AttributeType': 'N'}, # Stored as 0 (false) or 1 (true) for indexing
            {'AttributeName': 'isDeleted', 'AttributeType': 'N'}    # Stored as 0 (false) or 1 (true) for indexing
        ],
        'GlobalSecondaryIndexes': [
            {
                'IndexName': 'CourseIdIndex',
                'KeySchema': [
                    {'AttributeName': 'courseId', 'KeyType': 'HASH'}
                ],
                'Projection': {
                    'ProjectionType': 'ALL'
                },
                'ProvisionedThroughput': DEFAULT_PROVISIONED_THROUGHPUT
            },
            {
                'IndexName': 'UserIdIndex',
                'KeySchema': [
                    {'AttributeName': 'userId', 'KeyType': 'HASH'}
                ],
                'Projection': {
                    'ProjectionType': 'ALL'
                },
                'ProvisionedThroughput': DEFAULT_PROVISIONED_THROUGHPUT
            },
            {
                'IndexName': 'PublishedIndex',
                'KeySchema': [
                    {'AttributeName': 'isPublished', 'KeyType': 'HASH'}
                ],
                'Projection': {
                    'ProjectionType': 'ALL'
                },
                'ProvisionedThroughput': DEFAULT_PROVISIONED_THROUGHPUT
            },
            {
                'IndexName': 'DeletedIndex',
                'KeySchema': [
                    {'AttributeName': 'isDeleted', 'KeyType': 'HASH'}
                ],
                'Projection': {
                    'ProjectionType': 'ALL'
                },
                'ProvisionedThroughput': DEFAULT_PROVISIONED_THROUGHPUT
            }
        ],
        'ProvisionedThroughput': DEFAULT_PROVISIONED_THROUGHPUT
    },
    {
        'TableName': 'frames',
        'KeySchema': [
            {'AttributeName': 'movieId', 'KeyType': 'HASH'},
            {'AttributeName': 'frameNumber', 'KeyType': 'RANGE'}
        ],
        'AttributeDefinitions': [
            {'AttributeName': 'movieId', 'AttributeType': 'S'},
            {'AttributeName': 'frameNumber', 'AttributeType': 'N'}
        ],
        'ProvisionedThroughput': DEFAULT_PROVISIONED_THROUGHPUT
    }
]

# --- Function Definitions ---

def drop_dynamodb_table(table_name: str, dynamodb_resource: 'boto3.resources.base.ServiceResource'):
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
        table = dynamodb_resource.Table(table_name)
        table.delete() # Initiates the deletion process
        table.wait_until_not_exists()
        logger.info("Table %s deleted successfully!", table_name)

    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            logger.warning("Table %s does not exist.", table_name)
        elif e.response['Error']['Code'] == 'ValidationException' and "table is being deleted" in str(e):
            logger.warning("Table %s is already in the process of being deleted.", table_name)
        else:
            logger.error("Error deleting table %s: %s", table_name, e)
    except Exception as e:
        logger.error("Unexpected error occurred while deleting table %s: %s", table_name, e)


def create_dynamodb_tables(dynamodb_resource: 'boto3.resources.base.ServiceResource'):
    """Creates DynamoDB tables based on the configurations defined in TABLE_CONFIGURATIONS.

    Connects to the local DynamoDB instance using DEFAULT_DYNAMODB_ENDPOINT.

    :param dynamodb_resource: The boto3 DynamoDB resource object.
    :type dynamodb_resource: boto3.resources.base.ServiceResource
    :raises ClientError: If a DynamoDB client-side error occurs (e.g., table already exists).
    :raises Exception: For any unexpected errors during creation.
    """
    for table_config in TABLE_CONFIGURATIONS:
        table_name = table_config['TableName']
        logger.info("Attempting to create table: %s", table_name)
        try:
            table = dynamodb_resource.create_table(**table_config)
            logger.info("Waiting for table %s to be active...", table_name)
            table.wait_until_exists()
            logger.info("Table %s created successfully!", table_name)
        except ClientError as e:
            if e.response['Error']['Code'] == 'TableAlreadyExistsException':
                logger.warning("Table %s already exists.", table_name)
            else:
                logger.error("Error creating table %s: %s", table_name, e)
        except Exception as e:
            logger.error("An unexpected error occurred creating table %s: %s", table_name, e)

if __name__ == "__main__":
    # --- Argparse Setup ---
    parser = argparse.ArgumentParser(description="Manage DynamoDB Local tables (create/drop).")
    parser.add_argument(
        "--debug",
        action="store_true", # This flag will be True if --debug is present, False otherwise
        help="Set logging level to DEBUG for more verbose output."
    )
    args = parser.parse_args()

    # --- Configure Logging Level ---
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG) # Set root logger level to DEBUG
        logger.debug("Debug mode enabled.")
    else:
        logging.getLogger().setLevel(logging.INFO) # Default to INFO if not debug

    # Re-assign logger to ensure it uses the newly configured level from the root.
    logger = logging.getLogger(__name__)

    # Initialize DynamoDB resource once (now that logging level is set)
    dynamodb_resource = boto3.resource(
        'dynamodb',
        region_name='us-east-1',
        endpoint_url=DEFAULT_DYNAMODB_ENDPOINT
    )

    tables_to_drop = ['users', 'courses', 'movies', 'frames']
    for table_name in tables_to_drop:
        drop_dynamodb_table(table_name, dynamodb_resource) # Pass the resource
    create_dynamodb_tables(dynamodb_resource) # Pass the resource
