import uuid

from app import odbmaint
from app.constants import C


EXPECTED_TABLES = {
    "users",
    "unique_emails",
    "api_keys",
    "courses",
    "course_users",
    "movies",
    "movie_frames",
    "logs",
}


def test_load_table_configurations_reads_json_table_contract():
    configs = odbmaint.load_table_configurations()

    assert {config[odbmaint.TableName] for config in configs} == EXPECTED_TABLES
    assert all(config[odbmaint.BillingMode] == odbmaint.PAY_PER_REQUEST for config in configs)

    movies = None
    for config in configs:
        if config[odbmaint.TableName] == "movies":
            movies = config
            break

    assert movies is not None
    movie_index_names = {
        index[odbmaint.IndexName]
        for index in movies[odbmaint.GlobalSecondaryIndexes]
    }
    assert movie_index_names == {"course_id_idx", "user_id_idx"}


def test_load_table_configurations_returns_independent_copies():
    configs = odbmaint.load_table_configurations()
    configs[0][odbmaint.TableName] = "changed"

    fresh_configs = odbmaint.load_table_configurations()
    assert fresh_configs[0][odbmaint.TableName] == "users"


def test_create_tables_reports_creation_progress(local_ddb, monkeypatch):
    del local_ddb
    prefix = f"status-{uuid.uuid4()}-"
    messages = []
    monkeypatch.setenv(C.DYNAMODB_TABLE_PREFIX, prefix)
    monkeypatch.setattr(C, "TABLE_CREATE_SLEEP_TIME", 0)

    try:
        odbmaint.create_tables(status=messages.append)

        assert messages[:2] == [
            f"Creating 8 DynamoDB tables with prefix '{prefix}'. "
            "This usually takes 1-3 minutes in AWS.",
            "Tables are created sequentially; DynamoDB status checks may be 20 seconds apart.",
        ]
        table_names = [config[odbmaint.TableName] for config in odbmaint.load_table_configurations()]
        for table_number, table_name in enumerate(table_names, start=1):
            full_name = prefix + table_name
            assert f"[{table_number}/8] Creating {full_name}..." in messages
            assert f"[{table_number}/8] Waiting for {full_name} to become ACTIVE..." in messages
            assert f"[{table_number}/8] Ready: {full_name}" in messages

        messages.clear()
        odbmaint.create_tables(ignore_table_exists=True, status=messages.append)
        for table_number, table_name in enumerate(table_names, start=1):
            assert f"[{table_number}/8] Already exists: {prefix + table_name}" in messages
    finally:
        odbmaint.drop_tables(silent_warnings=True)
