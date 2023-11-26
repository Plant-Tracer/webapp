Files in this directory and the rational:


|-----|-----|
|app_test.py | Tests for the bottle application. These tests are implemented with boddle.
|dbreader_test.py | Tests to make sure that dbreader is accessible through the test framework
|endpoint_test.py | Actually tests a running endpoint. Creates the endpoint with `http_fixtureendpoint` fixture and tests it locally. Does not test remote endpoints. DOes not run if environment variable SKIP_ENDPOINT_TEST is set to YES|
|gravitropism_test.py| TODO |
|mailer_test.py | |
|movie_test.py | tests database functions involved in movie creation |
|tracker_test.py | tests tracking algorithms|
|user_test.py | tests database functions involved in user and course creation |
|fixtures/localmail_config.py | Experiment on moving fixtures to a subdirectory. Currently only used by mailer_test.py |



Files used in tests:

Environment variables used in testing:

SKIP_ENDPOINT_TEST - If YES, endpoint tests are not run
