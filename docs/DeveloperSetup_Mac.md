# Developer Setup Mac
This tutorial takes a new macOS install and gets you to running PlantTracer locally and on Amazon.

It makes use of the following services, which you will install:

|Service|Endpoint|Purpose|
|-----------|----|--------|
|DynamoDBLocal.jar|`http://localhost:8010/`|AWS DynamoDB Emulator
|Minio|`http://localhost:9100/`|AWS S3 Emulator


The following environment variables must be set to run Java programs on your Mac with homebrew (we install these below in your ~/.zshrc file):

|Variable|Value|
|--------|-----|
|`PATH`|Must include `/opt/homebrew/opt/openjdk/bin`|
|`CPPFLAGS`|Must include `-I/opt/homebrew/opt/openjdk/include`

The DynamoDBLocal and Minio programs require that the following AWS  variables be set. They can be set on the command line as environment variables (as is done in the `Makefile`), they can be set in your `~/.zshrc` file, or they can be in your `~/.aws/credentials` and `~/.aws/config` files:

|Variable|Value|
|--------|-----|
|`AWS_ACCESS_KEY_ID`|`minioadmin`|
|`AWS_SECRET_ACCESS_KEY`|`minioadmin`|
|`AWS_DEFAULT_REGION`|`us-east-1`|
|`AWS_ENDPOINT_URL_S3`|`http://localhost:9100/`|
|`AWS_ENDPOINT_URL_DYNAMODB`|`http://localhost:8010/`|

You will also want to set these variables:
|Variable|Value for `make pytest` in Github actions`|Purpose|
|--------|-----|----|
|`PLANTTRACER_S3_BUCKET`|`planttracer-local`|Bucket where videos are stored|
|`DYNAMODB_TABLE_PREFIX`|`demo-`|Prefix for all DynamoDB tables|

You may optionally set these variables:
|Variable|Value set for `make pytest` in Github actions|Purpose|
|--------|-----|----|
|`DEMO_COURSE_ID`|not set|If set, Plant Tracer runs in [demo mode](demo_mode.rst) and `DEMO_COURSE_ID` specifies the course that is viewed.|
|`LOG_LEVEL`|`DEBUG`|If set, all logging is at this log level|

Note that there are multiple ways that a single service can be sliced or partitioned:

* A single server might have multiple Plant Tracer web app instances listening on different ports.
* Each web app instance can store in its own S3 bucket. Alternatively, you can use the same S3 bucket for multiple web app instances, because each movie is stored with a UUID in the form `s3://{PLANTTRACER_S3_BUCKET/{COURSE_ID}/{MovieID/`. 
* Each web app instance stores its metadata in a set of DynamoDB tables that have a specific prefix. When testing with `pytest`, tables are created with the randomized prefix `test-????` where `????` is a randomly hexadecimal string.
* Within each web app instance, there can be one or more courses, each with its own course identifier (name).

Note that any course can be come a demo course. What makes it a demo course is that the web app instance has the `DEMO_COURSE_ID` environment variable set. This allows the same course to be accessed for non-demo purposes and demo purposes. When you access a web app instance that has the `DEMO_COURSE_ID` environment variable set, you are automatically authenticated as the demo user and can only access that user's movies and public movies.

# Mac Configuration
## Prep your mac
1. Install developer tools.
 
From a clean install, open the Terminal window and type `make`. You should get an error message:
<img width="949" height="455" alt="image" src="https://github.com/user-attachments/assets/a51cd276-7eae-4de8-8ba7-cea15ebe3bb6" />

* After a few moments, you'll see this window. Click **Install**:
<img width="573" height="307" alt="image" src="https://github.com/user-attachments/assets/21294734-0324-4b83-9a4a-1c4185dfa7aa" />

Agree to the license agreement.

2. Install `brew` from https://brew.sh/

```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```
   
<img width="1110" height="553" alt="image" src="https://github.com/user-attachments/assets/53738f7e-3168-4041-a211-f6d1058ae0bd" />
...
<img width="1110" height="553" alt="image" src="https://github.com/user-attachments/assets/03ccb527-14ba-4d0c-84d9-48bd337f93a1" />


(You will need to enter your password and type **RETURN/ENTER**.)

Follow the instructions and type:
```
echo >> /Users/simsong/.zprofile
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> /Users/simsong/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

2. Install OpenJDK (you need it for DynamoDBLocal)

```
brew install openjdk
echo 'export PATH="/opt/homebrew/opt/openjdk/bin:$PATH"' >> ~/.zshrc
echo 'export CPPFLAGS="-I/opt/homebrew/opt/openjdk/include"' >> ~/.zshrc
source ~/.zshrc
```

## Download and install the required software

1. Download the git repo.

```
% git clone --recursive https://github.com/Plant-Tracer/webapp.git
Cloning into 'webapp'...
remote: Enumerating objects: 10477, done.
remote: Counting objects: 100% (1404/1404), done.
remote: Compressing objects: 100% (577/577), done.
remote: Total 10477 (delta 866), reused 827 (delta 827), pack-reused 9073 (from 3)
Receiving objects: 100% (10477/10477), 106.38 MiB | 48.78 MiB/s, done.
Resolving deltas: 100% (7355/7355), done.
% 
```

2. Use the macOS installer built into the Makefile to install additional software
```
cd webapp
make install-macos
```

## Each time you reboot
Now you must start the servers. You will also need to do this every time you reboot and want to develop.

1. Start the local servers

```
make start_local_dynamodb
make start_local_minio
```

2. (First time through), make the local S3 bucket and verify it is there:

```
make make-local-bucket
make list-local-buckets
```

## Validate the release

1. Check to make sure the commit that you checked out is valid:
```
make pylint
make pytest
```
If these do not work, speak with a maintainer, as the build is broken.

# Developing locally
At this point you have checked out the git repo and verified that `make pylint` and `make pytest` run without error. This means:
* You have all the necessary software installed.
* DynamoDBlocal works
* Minio works.

Plant Tracer's webapp runs within a python virtual environment. You should `cd` into the top-level directory and activate the virtual environment in your command line shell, so that when you type `python` you run the correct python interpreter:

Note that our virtual environment is currently stored in the `venv` directory, although it is increasingly trendy to store the venv in `.venv` and we will be making this change at some point.

```
cd ~/gits/webapp          # or wherever you have it installed
source venv/bin/activate  
python --version          # Verify you get the correct python
```

When you run `pytest`, a directory called `var/` was created which contains the following files:

```
% ls -l var
total 22672
-rw-r--r--@ 1 simsong  staff         6 Jul 12 13:40 dynamodb_local.pid
-rw-r--r--@ 1 simsong  staff         6 Jul 12 13:40 minio.pid
drwxr-xr-x@ 3 simsong  staff        96 Jul 12 13:40 planttracer-local
-rw-r--r--@ 1 simsong  staff  10772480 Jul 12 13:40 shared-local-instance.db
```

* `dynamodb_local.pid` --- File containing the PID of the DynamoDBlocal process
* `minio.pid` --- File containing the PID of the minio process
* `planttracer-local` --- Directory containing the objects in the `s3://planttracer-local/` Minio S3 bucket.
* `shared-local-instance.db` --- SQLite 3.x database containing all of the objects in the DynamoDBlocal tables.

The bucket allows you to see how individual objects are stored in S3:
```
(venv) simsong@Seasons-2 webapp % find var/planttracer-local -type f
var/planttracer-local/demo-course/m0fa68c59-39ad-4166-8a07-7656b73ed74f_mp4.zip/xl.meta
var/planttracer-local/demo-course/m0fa68c59-39ad-4166-8a07-7656b73ed74f_mp4.zip/0fa25410-05dd-4f14-9eb5-bb3367f05b1f/part.1
var/planttracer-local/demo-course/m5dbcd625-06bb-4875-ae82-b218edfcb023.mov/8b6ab206-c2b0-4278-a931-b87bf49db6fd/part.1
var/planttracer-local/demo-course/m5dbcd625-06bb-4875-ae82-b218edfcb023.mov/xl.meta
var/planttracer-local/demo-course/mf97f7149-00d5-487e-8e75-df9b958a75ab/000000.jpg/xl.meta
var/planttracer-local/demo-course/mf97f7149-00d5-487e-8e75-df9b958a75ab.mov/xl.meta
var/planttracer-local/demo-course/mf97f7149-00d5-487e-8e75-df9b958a75ab.mov/6588491e-e797-4f0d-a16c-0aa65f742e52/part.1
var/planttracer-local/demo-course/mae9499f2-e9f2-4856-a353-ba26b04270ba.mov/xl.meta
var/planttracer-local/demo-course/mae9499f2-e9f2-4856-a353-ba26b04270ba.mov/931fdf84-c442-4896-8454-d21a3d94927d/part.1
var/planttracer-local/demo-course/m0fa68c59-39ad-4166-8a07-7656b73ed74f.mov/6922ff10-85d9-4e6b-a223-b0b33daa8595/part.1
var/planttracer-local/demo-course/m0fa68c59-39ad-4166-8a07-7656b73ed74f.mov/xl.meta
var/planttracer-local/demo-course/m0fa68c59-39ad-4166-8a07-7656b73ed74f/000000.jpg/xl.meta
(venv) simsong@Seasons-2 webapp %
```

There are two Makefile targets that you have to manage this:

* `make delete-local` - Just deletes the local directory and doesn't recreate anything
* `make wipe-local` - Wipes the `var/` directory and recreates the local bucket.

## Getting started
If you have reboot your computer, it's likely that none the databases are running.  To get going, you should do this:

```
make start_local_dynamodb
make start_local_minio
```

Here's what it looks like when it runs:
```
(venv) simsong@Seasons-2 webapp % make start_local_dynamodb
bash bin/local_dynamodb_control.bash start
Starting DynamoDB Local...
  Waiting for DynamoDBLocal to be ready (1)...
  Waiting for DynamoDBLocal to be ready (2)...
DynamoDB Local is ready.
DynamoDB Local started in the background (PID: 12336).
DynamoDB Local endpoint: http://localhost:8010
(venv) simsong@Seasons-2 webapp % make start_local_minio
bash bin/local_minio_control.bash start
Starting Minio ...
Minio Local started in the background (PID: 12428).
  Waiting for MinIO to be ready (1)...
  Waiting for MinIO to be ready (2)...
  Waiting for MinIO to be ready (3)...
  Waiting for MinIO to be ready (4)...
  Waiting for MinIO to be ready (5)...
MinIO is ready.
%
```


You can now create a web app instance within the DyanmoDBlocal and the Minio instances. This will:
* Create all of the tables with a specific prefix (that you will specify)
* Create a demo user  (created by `odbmaint.create_course()`)
* Create an admin user (also created by `odbmaint.create_course()`)
* Create the demo movies (created by `dbutil.populate_demo_movies()`)

Notice that below we set all of the environment variables first. You might want to do this in a file that your `source`. _We do not recommend that you put this in your `~/.bashrc` or `~/.zshrc` files, becuase setting these variables will cause problems if you need to use Amazon Web Services for something else.

```
(venv) simsong@Seasons-2 webapp % AWS_ENDPOINT_URL_DYNAMODB=http://localhost:8010/\
    AWS_ENDPOINT_URL_S3=http://localhost:9100/\
    AWS_ACCESS_KEY_ID=minioadmin \
    AWS_SECRET_ACCESS_KEY=minioadmin \
    AWS_DEFAULT_REGION=us-east-1 \
    PLANTTRACER_S3_BUCKET=planttracer-local \
    DYNAMODB_TABLE_PREFIX=dev- \
    LOG_LEVEL=DEBUG python dbutil.py --createdb
2025-08-10 09:43:16,090  odb.py:376 WARNING: NOTE: create_user does not check to make sure user admin@planttracer.com's course demo-course exists
Transaction succeeded: user inserted.
2025-08-10 09:43:16,131  odb.py:376 WARNING: NOTE: create_user does not check to make sure user demo@planttracer.com's course demo-course exists
Transaction succeeded: user inserted.
2025-08-10 09:43:16,154  odb.py:1302 WARNING: INEFFICIENT CALL. Just return movie_id.course_id
2025-08-10 09:43:16,309  odb.py:1302 WARNING: INEFFICIENT CALL. Just return movie_id.course_id
(venv) simsong@Seasons-2 webapp %
```

Notice that the admin user's email is assumed to be `admin@planttracer.com` and the demo user's email is `demo@planttracer.com`.

That `WARNING: INEFFICIENT CALL` is a note to the developer that this code could be cleaned up at some point in the future.

(We could have just run `make make-local-demo`, but here we expand so that you can see all of the variables.)



Now we can run the web app:
```
(venv) simsong@Seasons-2 webapp % AWS_ENDPOINT_URL_DYNAMODB=http://localhost:8010/ \
    AWS_ENDPOINT_URL_S3=http://localhost:9100/ \
    AWS_ACCESS_KEY_ID=minioadmin \
    AWS_SECRET_ACCESS_KEY=minioadmin \
    AWS_DEFAULT_REGION=us-east-1 \
    PLANTTRACER_S3_BUCKET=planttracer-local \
    DYNAMODB_TABLE_PREFIX=dev- \
    LOG_LEVEL=DEBUG venv/bin/flask --debug --app deploy.app.bottle_app:app run --port 8080 --with-threads
2025-08-10 09:49:33,073  bottle_app.py:59 INFO: new Flask(__name__=webapp.deploy.app.bottle_app) log_level=DEBUG
2025-08-10 09:49:33,073  db_object.py:72 DEBUG: make_urn urn=s3://planttracer-local/
2025-08-10 09:49:33,073  bottle_app.py:60 INFO: make_urn('')=s3://planttracer-local/
 * Serving Flask app 'deploy.app.bottle_app:app'
 * Debug mode: on
2025-08-10 09:49:33,126  _internal.py:97 INFO: WARNING: This is a development server. Do not use it in a production deployment. Use a production WSGI server instead.
 * Running on http://127.0.0.1:8080
2025-08-10 09:49:33,127  _internal.py:97 INFO: Press CTRL+C to quit
2025-08-10 09:49:33,127  _internal.py:97 INFO:  * Restarting with stat
2025-08-10 09:49:33,375  bottle_app.py:59 INFO: new Flask(__name__=webapp.deploy.app.bottle_app) log_level=DEBUG
2025-08-10 09:49:33,375  db_object.py:72 DEBUG: make_urn urn=s3://planttracer-local/
2025-08-10 09:49:33,375  bottle_app.py:60 INFO: make_urn('')=s3://planttracer-local/
2025-08-10 09:49:33,393  _internal.py:97 WARNING:  * Debugger is active!
2025-08-10 09:49:33,402  _internal.py:97 INFO:  * Debugger PIN: 594-409-847
```

(Once again, you could just do a `make run-local-debug`.)

Now connect to `http://127.0.0.1:8080`:

<img width="1024" height="677" alt="image" src="https://github.com/user-attachments/assets/57585fc5-1db7-4f09-926f-bcf7476f2819" />

There's not much you can do at this point until we create a course and a user

## Creating a course and a user
While the application is running, open another window. 

We will first use the `--report` option to see what is in the database:
```
simsong@Seasons-2 ~ % cd gits/webapp
simsong@Seasons-2 webapp % source venv/bin/activate
(venv) simsong@Seasons-2 webapp % AWS_ENDPOINT_URL_DYNAMODB=http://localhost:8010/ AWS_ENDPOINT_URL_S3=http://localhost:9100/ AWS_ACCESS_KEY_ID=minioadmin AWS_SECRET_ACCESS_KEY=minioadmin AWS_DEFAULT_REGION=us-east-1 PLANTTRACER_S3_BUCKET=planttracer-local DYNAMODB_TABLE_PREFIX=dev- LOG_LEVEL=INFO python dbutil.py --report
2025-08-10 09:53:21,580  odbmaint.py:347 WARNING: scan table dynamodb.Table(name='dev-api_keys')
2025-08-10 09:53:21,583  odbmaint.py:347 WARNING: scan table dynamodb.Table(name='dev-users')
2025-08-10 09:53:21,586  odbmaint.py:347 WARNING: scan table dynamodb.Table(name='dev-movies')
2025-08-10 09:53:21,588  odbmaint.py:347 WARNING: scan table dynamodb.Table(name='dev-movie_frames')
2025-08-10 09:53:21,592  odbmaint.py:347 WARNING: scan table dynamodb.Table(name='dev-courses')
2025-08-10 09:53:21,594  odbmaint.py:347 WARNING: scan table dynamodb.Table(name='dev-course_users')
2025-08-10 09:53:21,596  odbmaint.py:347 WARNING: scan table dynamodb.Table(name='dev-logs')
table               .item_count    count_table_items()
----------------  -------------  ---------------------
dev-api_keys                  1                      1
dev-users                     2                      2
dev-movies                    2                      2
dev-movie_frames              0                      0
dev-courses                   1                      1
dev-course_users              2                      2
dev-logs                      0                      0
(venv) simsong@Seasons-2 webapp %
```
Notice that our code automatically generates a WARNING of every table scan operaiton, as these operaitons are typically expensive in DynamoDB. This is just for development purposes.  (The report option will be expanded over time.)

Notice that there is only one API_KEY but there are two users. This means that one of the users cannot log in. To facilitate local developiong, we want to use the `--makelink` option for the admin user. 

