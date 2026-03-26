import boto3
import json
from decimal import Decimal
from boto3.dynamodb.conditions import Key
import sys

# Helper to handle DynamoDB's Decimal types
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            if obj % 1 == 0:
                return int(obj)
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

def dump_movie_frames(table_name, movie_id):
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table(table_name) # <-- Insert your table name

    # Use query() instead of scan() to fetch only this movie's frames
    response = table.query(
        KeyConditionExpression=Key('movie_id').eq(movie_id)
    )
    items = response.get('Items', [])

    # Dump to clean JSON
    json.dump(items, sys.stdout, cls=DecimalEncoder, indent=4)
    print(f"Successfully dumped {len(items)} frames for movie {movie_id}")

if __name__=="__main__":
    dump_movie_frames(sys.argv[1], sys.argv[2])
