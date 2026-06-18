import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def test_release_docs_reference_current_artifacts() -> None:
    version = _version()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    site = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    combined = readme + site

    assert f"releases/download/v{version}/promptcloak-{version}-py3-none-any.whl" in combined
    assert f"releases/download/v{version}/promptcloak-{version}.tgz" in combined
    assert f"ghcr.io/bvolpato/promptcloak:{version}" in combined
    assert "0.1.3" not in combined


def test_docs_do_not_claim_pypi_install() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    site = (ROOT / "site" / "index.html").read_text(encoding="utf-8")

    assert "uv add promptcloak" not in readme
    assert "uv add promptcloak" not in site
