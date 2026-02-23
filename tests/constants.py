"""
Shared constants for tests: fixture dict keys and test data paths.
Import from here instead of tests.fixtures.local_aws so tests do not depend on the fixtures package.
"""

import os

from app.paths import TEST_DATA_DIR

# Keys used in fixture return dicts (e.g. new_course, new_movie)
ADMIN_EMAIL = 'admin_email'
MOVIE_TITLE = 'movie_title'

# Test data file paths
TEST_PLANTMOVIE_PATH = os.path.join(TEST_DATA_DIR, "2019-07-31 plantmovie.mov")
TEST_PLANTMOVIE_ROTATED_PATH = os.path.join(TEST_DATA_DIR, "2019-07-31 plantmovie-rotated.mov")
TEST_CIRCUMNUTATION_PATH = os.path.join(TEST_DATA_DIR, "2019-07-12 circumnutation.mp4")
