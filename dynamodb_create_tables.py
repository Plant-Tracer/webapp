import logging

import boto3
from botocore.exceptions import ClientError

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_DYNAMODB_ENDPOINT = 'http://localhost:8010'
DEFAULT_PROVISIONED_THROUGHPUT = { 'ReadCapacityUnits': 1,
                                   'WriteCapacityUnits': 1 }

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
        'ProvisionedThroughput': DEFAULT_PROVISIONED_THROUGHPUT # Using the factored-out value
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
            {'AttributeName': 'isPublished', 'AttributeType': 'N'}, # 1 means published
            {'AttributeName': 'isDeleted', 'AttributeType': 'N'} # 1 means deleted
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
                'ProvisionedThroughput': DEFAULT_PROVISIONED_THROUGHPUT # Using the factored-out value
            },
            {
                'IndexName': 'UserIdIndex',
                'KeySchema': [
                    {'AttributeName': 'userId', 'KeyType': 'HASH'}
                ],
                'Projection': {
                    'ProjectionType': 'ALL'
                },
                'ProvisionedThroughput': DEFAULT_PROVISIONED_THROUGHPUT # Using the factored-out value
            },
            {
                'IndexName': 'PublishedIndex',
                'KeySchema': [
                    {'AttributeName': 'isPublished', 'KeyType': 'HASH'}
                ],
                'Projection': {
                    'ProjectionType': 'ALL' # Or KEYS_ONLY / INCLUDE specific attributes
                },
                'ProvisionedThroughput': DEFAULT_PROVISIONED_THROUGHPUT
            },
            {
                'IndexName': 'DeletedIndex',
                'KeySchema': [
                    # Using 'isDeleted' as the HASH key for this index
                        {'AttributeName': 'isDeleted', 'KeyType': 'HASH'}
                ],
                'Projection': {
                    'ProjectionType': 'ALL' # Or KEYS_ONLY / INCLUDE specific attributes
                },
                'ProvisionedThroughput': DEFAULT_PROVISIONED_THROUGHPUT
            }

            ],
        'ProvisionedThroughput': DEFAULT_PROVISIONED_THROUGHPUT # Using the factored-out value
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
        'ProvisionedThroughput': DEFAULT_PROVISIONED_THROUGHPUT # Using the factored-out value
    }
]

def drop_dynamodb_table(table_name):
    """
    Drops a specified DynamoDB table from the local instance.
    """

    # Connect to DynamoDBLocal
    dynamodb = boto3.resource( 'dynamodb',
                               region_name='us-east-1', # Region can be anything for local, but needed
                               endpoint_url=DEFAULT_DYNAMODB_ENDPOINT )

    logger.info("Attempting to delete table: %s",table_name)
    try:
        table = dynamodb.Table(table_name)
        table.delete() # Initiates the deletion process
        table.wait_until_not_exists()
        logger.info("Table %s deleted successfully!",table_name)

    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            logger.warning("Table %s does not exist.",table_name)
        elif e.response['Error']['Code'] == 'ValidationException' and "table is being deleted" in str(e):
            logger.warning("Table %s is already in the process of being deleted.",table_name)
        else:
            logging.error("Error deleting table %s:%s",table_name,e)
    except Exception as e:
        logging.error("Uexpected error occurred while deleting table %s:%s",table_name,e)


def create_dynamodb_tables():
    """
    Connects to DynamoDBLocal and creates tables based on a defined configuration,
    using a factored-out default provisioned capacity.
    """
    # Define default provisioned throughput at the top
    # This will be used for all tables and GSIs unless explicitly overridden

    # Connect to DynamoDBLocal
    dynamodb = boto3.resource(
        'dynamodb',
        region_name='us-east-1', # Region can be anything for local, but needed
        endpoint_url='http://localhost:8010'
    )

    # Define table configurations in a list of dictionaries
    table_configurations = TABLE_CONFIGURATIONS

    # Loop through each table configuration and attempt to create the table
    for table_config in table_configurations:
        table_name = table_config['TableName']
        print(f"Attempting to create table: {table_name}")
        try:
            table = dynamodb.create_table(**table_config)
            logging.info("Waiting for table %s to be active...",table_name)
            table.wait_until_exists()
            logging.info("Table %s created successfully!",table_name)
        except ClientError as e:
            if e.response['Error']['Code'] == 'TableAlreadyExistsException':
                logging.warning("Table %s already exists.",table_name)
            else:
                logging.error("Error creating table %s:%s",table_name,e)
        except Exception as e:
            logging.error("An unexpected error occurred creating table %s; %s",table_name,e)

if __name__ == "__main__":
    tables_to_drop = ['users', 'courses', 'movies', 'frames']
    for table_name in tables_to_drop:
        drop_dynamodb_table(table_name)
    create_dynamodb_tables()
