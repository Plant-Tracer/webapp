from app import odbmaint


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
