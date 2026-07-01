"""Tests for CLI commands."""

import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from webhook_router.cli import main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def sample_config_file():
    """Create a temporary config file."""
    data = """\
routes:
  - name: "test-route"
    filter:
      event_types: ["push"]
    destinations:
      - name: "dest1"
        type: "console"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(data)
        f.flush()
        yield f.name
    Path(f.name).unlink(missing_ok=True)


class TestCLI:
    """Tests for CLI commands."""

    def test_version(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_sample_config(self, runner):
        result = runner.invoke(main, ["sample-config"])
        assert result.exit_code == 0
        assert "server:" in result.output
        assert "routes:" in result.output
        assert "github-events" in result.output

    def test_sample_config_to_file(self, runner):
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            output_path = f.name

        try:
            result = runner.invoke(main, ["sample-config", "-o", output_path])
            assert result.exit_code == 0
            assert Path(output_path).exists()
            content = Path(output_path).read_text()
            assert "routes:" in content
        finally:
            Path(output_path).unlink(missing_ok=True)

    def test_validate_valid_config(self, runner, sample_config_file):
        result = runner.invoke(main, ["validate", "-c", sample_config_file])
        assert result.exit_code == 0
        assert "valid" in result.output.lower() or "✓" in result.output

    def test_validate_missing_file(self, runner):
        result = runner.invoke(main, ["validate", "-c", "/nonexistent/config.yaml"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_routes_command(self, runner, sample_config_file):
        result = runner.invoke(main, ["routes", "-c", sample_config_file])
        assert result.exit_code == 0
        assert "test-route" in result.output

    def test_start_missing_config(self, runner):
        result = runner.invoke(main, ["start", "-c", "/nonexistent/config.yaml"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_verbose_flag(self, runner):
        result = runner.invoke(main, ["--verbose", "sample-config"])
        assert result.exit_code == 0
