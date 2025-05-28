import uuid
import boto3

# Assuming dynamodb resource is already initialized (as in your script)
dynamodb = boto3.resource(
    'dynamodb',
    region_name='us-east-1',
    endpoint_url='http://localhost:8010'
)

# --- Example for 'users' table ---
users_table = dynamodb.Table('users')

# Generate a unique ID for the new user
new_user_id = str(uuid.uuid4()) # uuid.uuid4() generates a UUID object, convert to string

user_data = {
    'id': new_user_id,
    'email': 'new.user@example.com',
    'username': 'newUser123',
    'firstName': 'New',
    'lastName': 'User',
    'primaryCourseId': 'course-abc-123' # Example of other attributes
    # 'courseIds': ['course-abc-123', 'course-xyz-456'] # Example for multiple courses
}

try:
    users_table.put_item(Item=user_data)
    print(f"User '{user_data['username']}' with ID '{new_user_id}' added successfully.")
except Exception as e:
    print(f"Error adding user: {e}")


# --- Example for 'movies' table ---
movies_table = dynamodb.Table('movies')

new_movie_id = str(uuid.uuid4()) # Generate ID for movie

movie_data = {
    'id': new_movie_id,
    'title': 'My New Awesome Movie',
    'courseId': 'course-abc-123', # Link to a course ID
    'userId': new_user_id,        # Link to the user created above
    'isPublished': False,
    'isDeleted': False,
    'description': 'A fantastic new movie project.'
}

try:
    movies_table.put_item(Item=movie_data)
    print(f"Movie '{movie_data['title']}' with ID '{new_movie_id}' added successfully.")
except Exception as e:
    print(f"Error adding movie: {e}")

# --- Example for 'courses' table ---
courses_table = dynamodb.Table('courses')

new_course_id = str(uuid.uuid4()) # Generate ID for course

course_data = {
    'id': new_course_id,
    'name': 'Introduction to DynamoDB',
    'instructorId': new_user_id # Example: User is also an instructor
}

try:
    courses_table.put_item(Item=course_data)
    print(f"Course '{course_data['name']}' with ID '{new_course_id}' added successfully.")
except Exception as e:
    print(f"Error adding course: {e}")
