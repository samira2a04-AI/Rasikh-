import pytest

@pytest.fixture(scope="session", autouse=True)
def seed_test_db():
    """Seed the test database before any tests run.
    Executes the project's data loading script which populates the SQLite
    test database with required seed records (including Request L-C-001).
    """
    # Import inside the fixture to avoid side effects at import time.
    from scripts.load_data import main as load_data_main

    # Run the load script; it will use the same SessionLocal configured in
    # app.database.connection which points to the test SQLite DB by default.
    exit_code = load_data_main()
    assert exit_code == 0, "Data loading script failed during test setup"
