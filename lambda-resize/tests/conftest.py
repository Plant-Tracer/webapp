import logging

# Suppress verbose logging from urllib3 and selenium
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('selenium').setLevel(logging.WARNING)
