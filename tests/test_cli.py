from typer.testing import CliRunner

from promptcloak.cli import app
from promptcloak.version import __version__


def test_version_command() -> None:
    result = CliRunner().invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.output.strip() == __version__


def test_version_option() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == __version__


def test_init_defaults_to_openai(tmp_path) -> None:
    config = tmp_path / "config.yaml"

    result = CliRunner().invoke(app, ["init", "--config", str(config)])

    assert result.exit_code == 0
    data = config.read_text(encoding="utf-8")
    assert "default_base_url: https://api.openai.com/v1" in data
    assert "api_key: ${OPENAI_API_KEY}" in data
