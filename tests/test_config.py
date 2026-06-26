"""Tests for webhook router config loader."""

import tempfile
from pathlib import Path

import pytest
import yaml

from webhook_router.config import load_config, load_config_dict
from webhook_router.models import Config


class TestLoadConfig:
    """Tests for YAML config loading."""

    def test_load_valid_config(self):
        data = {
            "routes": [
                {
                    "name": "test-route",
                    "filter": {},
                    "destinations": [
                        {
                            "name": "dest1",
                            "type": "console",
                        }
                    ],
                }
            ]
        }
        config = load_config_dict(data)
        assert len(config.routes) == 1
        assert config.routes[0].name == "test-route"

    def test_load_from_file(self):
        data = {
            "routes": [
                {
                    "name": "file-route",
                    "filter": {},
                    "destinations": [
                        {
                            "name": "dest1",
                            "type": "file",
                            "file_path": "./logs/test.json",
                        }
                    ],
                }
            ]
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(data, f)
            f.flush()
            config = load_config(f.name)
        assert config.routes[0].name == "file-route"
        Path(f.name).unlink()

    def test_load_missing_file(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.yaml")

    def test_load_invalid_yaml(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("{{invalid yaml:::")
            f.flush()
            with pytest.raises(Exception):
                load_config(f.name)
        Path(f.name).unlink()

    def test_load_non_mapping_yaml(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("- list item\n")
            f.flush()
            with pytest.raises(ValueError, match="mapping"):
                load_config(f.name)
        Path(f.name).unlink()

    def test_load_default_values(self):
        data = {
            "routes": [
                {
                    "name": "minimal",
                    "destinations": [
                        {"name": "d", "type": "console"}
                    ],
                }
            ]
        }
        config = load_config_dict(data)
        assert config.server.host == "0.0.0.0"
        assert config.server.port == 8080
        assert config.signature.enabled is False
        assert config.rate_limit.enabled is False
