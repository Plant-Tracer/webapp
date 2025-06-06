import logging
import argparse
import copy

import boto3
from tabulate import tabulate
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr


from .odb import DDBO
from .constants import C

# Configure basic logging
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

KeySchema = 'KeySchema'
KeyType = 'KeyType'
TableName = 'TableName'
AttributeName = 'AttributeName'
AttributeType = 'AttributeType'
AttributeDefinitions = 'AttributeDefinitions'
GlobalSecondaryIndexes = 'GlobalSecondaryIndexes'
BillingMode = 'BillingMode'
PAY_PER_REQUEST = 'PAY_PER_REQUEST'
HASH = 'HASH'
RANGE = 'RANGE'
S = 'S'                         # string
N = 'N'                         # number

billing = {BillingMode: PAY_PER_REQUEST} # alternative is provisioned throughput
projection_all = {'Projection':{'ProjectionType':'ALL'}} # use all keys in index

# Define all table configurations as a global constant
# Note:
# courses - each course needs to know all of its users. They are stored in user_ids[]

TABLE_CONFIGURATIONS = [
    {
        TableName: 'users',
        KeySchema: [
            {AttributeName: 'user_id', KeyType: HASH}
        ],
        AttributeDefinitions: [
            {AttributeName: 'user_id', AttributeType: S},
            {AttributeName: 'email', AttributeType: S}
        ],
        GlobalSecondaryIndexes: [
            {
                'IndexName': 'email_idx',
                KeySchema: [
                    {AttributeName: 'email', KeyType: HASH}
                ],
                **projection_all,
            }
        ],
        **billing,
    },
    {
        TableName: 'unique_emails',
        KeySchema: [
            {AttributeName: 'email', KeyType: HASH}
        ],
        AttributeDefinitions: [
            {AttributeName: 'email', AttributeType: S}
        ],
        **billing,
    },
    {
        TableName: 'api_keys',
        KeySchema: [
            {AttributeName: 'api_key', KeyType: HASH}
        ],
        AttributeDefinitions : [
            {AttributeName: 'api_key', AttributeType : S},
            {AttributeName: 'user_id', AttributeType : S}
        ],
        GlobalSecondaryIndexes: [
            {
                'IndexName': 'user_id_idx',
                KeySchema: [
                    {AttributeName: 'user_id', KeyType: HASH}
                ],
                **projection_all,
            },
        ],
        **billing,
    },
    {
        TableName: 'courses',
        KeySchema: [
            {AttributeName: 'course_id', KeyType: HASH}
        ],
        AttributeDefinitions: [
            {AttributeName: 'course_id', AttributeType: S},
            {AttributeName: 'course_key', AttributeType: S}
        ],
        GlobalSecondaryIndexes : [
            {
                'IndexName': 'course_key_idx',
                KeySchema: [
                    {AttributeName: 'course_key', KeyType: HASH}
                ],
                **projection_all,
            },
            {
                'IndexName': 'course_id_idx',
                KeySchema: [
                    {AttributeName: 'course_id', KeyType: HASH}
                ],
                **projection_all,
            },
        ],
        **billing,
    },
    {
        TableName: 'movies',
        KeySchema: [
            {AttributeName: 'movie_id', KeyType: HASH}
        ],
        AttributeDefinitions: [
            {AttributeName: 'movie_id', AttributeType: S},
            {AttributeName: 'course_id', AttributeType: S},
            {AttributeName: 'user_id', AttributeType: S},
        ],
        GlobalSecondaryIndexes: [
            {
                'IndexName': 'course_id_idx',
                KeySchema: [
                    {AttributeName: 'course_id', KeyType: HASH}
                ],
                **projection_all,
            },
            {
                'IndexName': 'user_id_idx',
                KeySchema: [
                    {AttributeName: 'user_id', KeyType: HASH}
                ],
                **projection_all,
            },
        ],
        **billing,
    },
    {
        TableName: 'movie_frames',
        KeySchema: [
            {AttributeName: 'movie_id', KeyType: HASH},
            {AttributeName: 'frame_number', KeyType: RANGE}
        ],
        AttributeDefinitions: [
            {AttributeName: 'movie_id', AttributeType: S},
            {AttributeName: 'frame_number', AttributeType: N}
        ],
        **billing,
    },
    {
        TableName: 'logs',
        KeySchema: [
            {AttributeName: 'log_id', KeyType: HASH}
        ],
        AttributeDefinitions: [
            {AttributeName: 'log_id', KeyType: HASH},
            {AttributeName: 'ipaddr', AttributeType: S},
            {AttributeName: 'user_id', AttributeType: S},
            {AttributeName: 'course_id', AttributeType: S},
            {AttributeName: 'time_t', AttributeType: N},

        ],
        GlobalSecondaryIndexes: [
            {
                'IndexName': 'ipaddr_idx',
                KeySchema: [
                    {AttributeName: 'ipaddr', KeyType: HASH}
                ],
                'Projection': {
                    'ProjectionType' : 'INCLUDE',
                    'NonKeyAttributes' : ['log_id']
                }
            },
            {
                'IndexName': 'user_id_idx',
                KeySchema: [
                    {AttributeName: 'user_id', KeyType: HASH}
                ],
                'Projection': {
                    'ProjectionType' : 'INCLUDE',
                    'NonKeyAttributes' : ['log_id']
                }
            },
            {
                'IndexName': 'course_time_t_idx',
                KeySchema: [
                    {AttributeName: 'course_id', KeyType: HASH},
                    {AttributeName: 'time_t', KeyType: RANGE}
                ],
                'Projection': {
                    'ProjectionType' : 'INCLUDE',
                    'NonKeyAttributes' : ['log_id']
                }
            },
        ],
        **billing,
    }]



def drop_dynamodb_table(ddbo, table_name: str):
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
        table = ddbo.dynamodb.Table(table_name)
        table.delete() # Initiates the deletion process
        table.wait_until_not_exists()
        logger.info("Table %s deleted successfully!", table_name)

    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            logger.info("Table %s does not exist when dropping table.", table_name)
        elif e.response['Error']['Code'] == 'ValidationException' and "table is being deleted" in str(e):
            logger.info("Table %s is already in the process of being deleted.", table_name)
        else:
            logger.error("Error deleting table %s: %s", table_name, e)
    except Exception as e:
        logger.error("Unexpected error occurred while deleting table %s: %s", table_name, e)


def create_tables(ddbo, ignore_table_exists = set()):
    """Creates DynamoDB tables based on the configurations defined in TABLE_CONFIGURATIONS.

    Connects to the local DynamoDB instance using DEFAULT_DYNAMODB_ENDPOINT.

    :param dynamodb_resource: The boto3 DynamoDB resource object.
    :type dynamodb_resource: boto3.resources.base.ServiceResource
    :raises ClientError: If a DynamoDB client-side error occurs (e.g., table already exists).
    :raises Exception: For any unexpected errors during creation.
    """
    for table_config in TABLE_CONFIGURATIONS:
        # prepend the prefix to the table name before creating it
        tc = copy.deepcopy(table_config)
        tc[TableName] = table_name = ddbo.table_prefix + tc[TableName]
        logger.info("Attempting to create table: %s", table_name)
        try:
            table = ddbo.dynamodb.create_table(**tc)
            logger.info("Waiting for table %s to be active...", table_name)
            table.wait_until_exists()
            logger.info("Table %s created successfully!", table_name)
        except ClientError as e:
            if e.response['Error']['Code'] == 'TableAlreadyExistsException':
                if table_name not in ignore_table_exists:
                    logger.warning("Table %s already exists.", table_name)
            else:
                logger.error("Error creating table %s: %s", table_name, e)
        except Exception as e:
            logger.error("An unexpected error occurred creating table %s: %s", table_name, e)

def drop_tables(ddbo):
    tables_to_drop = [ ddbo.table_prefix + config[TableName] for config in TABLE_CONFIGURATIONS ]
    for table_name in tables_to_drop:
        drop_dynamodb_table(ddbo, table_name)

def puge_all_movies(ddbo):
    """"Deleting an entire table is significantly more efficient than removing items one-by-one,
    which essentially doubles the write throughput as you do as many delete operations as put operations.
    """
    ddbo.dynamodb.delete_table(TableName = ddbo.table_prefix + 'movies')
    create_tables(ddbo, ignore_table_exists={ddbo.table_prefix + 'movies'})

#pylint: disable=too-many-arguments
def create_course(ddbo, *, course_id, course_key, course_name, admin_email,
                  admin_name,max_enrollment=C.DEFAULT_MAX_ENROLLMENT,
                  demo_email = None):
    course = ddbo.get_course(course_id)
    if course:
        raise KeyError(f"Course {course_id} already exists")

    admin = ddbo.get_user(email=admin_email)
    if demo_email:
        demo = ddbo.get_user(email=demo_email)
    else:
        demo = False

    ddbo.put_course({'course_id':course_id,
                     'course_key':course_key,
                     'course_name':course_name,
                     'max_enrollment':max_enrollment })


    odb.create_course(course_key = course_key,
                      course_name = course_name,
                      max_enrollment = max_enrollment)
    admin_id = db.register_email(email=admin_email, course_key=course_key, name=admin_name)['user_id']
    db.make_course_admin(email=admin_email, course_key=course_key)
    logging.info("generated course_key=%s  admin_email=%s admin_id=%s",course_key,admin_email,admin_id)

    if demo_email:
        user_dir = db.register_email(email=demo_email, course_key = course_key, name=DEMO_NAME, demo_user=1)
        user_id = user_dir['user_id']
        db.make_new_api_key(email=demo_email)
        ct = 1
        for fn in os.listdir(TEST_DATA_DIR):
            ext = os.path.splitext(fn)[1]
            if ext in ['.mp4','.mov']:
                with open(os.path.join(TEST_DATA_DIR, fn), 'rb') as f:
                    movie_data = f.read()
                    movie_id = db.create_new_movie(user_id=user_id,
                                        title=DEMO_MOVIE_TITLE.format(ct=ct),
                                        description=DEMO_MOVIE_DESCRIPTION)
                    db.set_movie_data(movie_id=movie_id, movie_data = movie_data)
                ct += 1
    return admin_id

def add_admin_to_course(*, admin_email, course_id=None, course_key=None):
    db.make_course_admin(email=admin_email, course_key=course_key, course_id=course_id)

def remove_admin_from_course(*, admin_email, course_id=None, course_key=None, course_name=None):
    db.remove_course_admin(
                        email=admin_email,
                        course_key=course_key,
                        course_id=course_id,
                        course_name=course_name
                    )



def count_table_items(table, **kwargs):
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

    print("")
    kwargs =  { 'FilterExpression': Attr('demo').eq(1) }
    print("Number of demo users:", count_table_items(ddbo.users,  **kwargs))


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
        logger.setLevel(logging.DEBUG) # Set root logger level to DEBUG
        logger.debug("Debug mode enabled.")
    else:
        logger.setLevel(logging.INFO) # Default to INFO if not debug
    ddbo = DDBO(endpoint_url=C.DEFAULT_DYNAMODB_ENDPOINT)
    drop_tables(ddbo)
    create_tables(ddbo)
