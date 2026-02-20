"""Tests for configuration management."""
import os

import pytest


class TestConfig:
    def test_db_config_has_required_keys(self):
        from build_kg.config import DB_CONFIG

        assert "host" in DB_CONFIG
        assert "port" in DB_CONFIG
        assert "database" in DB_CONFIG
        assert "user" in DB_CONFIG
        assert "password" in DB_CONFIG

    def test_db_config_defaults(self):
        from build_kg.config import DB_CONFIG

        assert DB_CONFIG["host"] == os.getenv("DB_HOST", "localhost")
        assert isinstance(DB_CONFIG["port"], int)

    def test_openai_config_exists(self):
        from build_kg.config import OPENAI_MODEL

        assert OPENAI_MODEL  # Should have a default

    def test_age_graph_name_exists(self):
        from build_kg.config import AGE_GRAPH_NAME

        assert AGE_GRAPH_NAME  # Should have a default

    def test_parser_config_types(self):
        from build_kg.config import BATCH_SIZE, MAX_WORKERS, RATE_LIMIT_DELAY

        assert isinstance(BATCH_SIZE, int)
        assert isinstance(MAX_WORKERS, int)
        assert isinstance(RATE_LIMIT_DELAY, float)
        assert BATCH_SIZE > 0
        assert MAX_WORKERS > 0
        assert RATE_LIMIT_DELAY >= 0

    def test_validate_config_raises_without_credentials(self):
        from build_kg.config import DB_CONFIG, OPENAI_API_KEY, validate_config

        # Only test if credentials are not set
        if not DB_CONFIG["password"] or not OPENAI_API_KEY:
            with pytest.raises(ValueError, match="Configuration errors"):
                validate_config()
