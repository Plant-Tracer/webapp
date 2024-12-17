import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger(__name__)

def dump_files(path="."):
    import logging
    import os
    for (root, dirs, files) in os.walk(path):
        for fn in files:
            logging.error("%s/%s",root,fn)

if os.environ.get('DEBUG_DUMP_FILES', 'NO') == 'YES':
    dump_files('/')


from apig_wsgi import make_lambda_handler
from bottle_app import app

# Configure this as your entry point in AWS Lambda
lambda_handler = make_lambda_handler(app)

#  Run a local webserver with uvicorn?
if __name__ == "__main__":
    print("open http://localhost:8000/")
    uvicorn.run("bottle_app:app", port=8000, reload=True)
    import uvicorn
