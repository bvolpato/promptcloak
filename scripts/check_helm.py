#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "pyyaml==6.0.3",
# ]
# ///
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "promptcloak"


def render(*args: str) -> list[dict[str, Any]]:
    result = subprocess.run(
        ["helm", "template", "promptcloak", str(CHART), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return [item for item in yaml.safe_load_all(result.stdout) if isinstance(item, dict)]


def deployment(documents: list[dict[str, Any]]) -> dict[str, Any]:
    return next(item for item in documents if item.get("kind") == "Deployment")


def assert_server_auth_secret(document: dict[str, Any], expected_name: str) -> None:
    container = document["spec"]["template"]["spec"]["containers"][0]
    auth = next(item for item in container["env"] if item["name"] == "PROMPTCLOAK_SERVER_API_KEY")
    actual_name = auth["valueFrom"]["secretKeyRef"]["name"]
    if actual_name != expected_name:
        raise SystemExit(f"server auth references {actual_name!r}, expected {expected_name!r}")


def main() -> None:
    default_documents = render()
    assert_server_auth_secret(deployment(default_documents), "promptcloak-secret")
    if not any(item.get("kind") == "Secret" for item in default_documents):
        raise SystemExit("default chart did not render managed Secret")

    external_documents = render("--set", "existingSecret=promptcloak-env")
    external_deployment = deployment(external_documents)
    assert_server_auth_secret(external_deployment, "promptcloak-env")
    container = external_deployment["spec"]["template"]["spec"]["containers"][0]
    if container.get("envFrom") != [{"secretRef": {"name": "promptcloak-env"}}]:
        raise SystemExit("existing Secret is not loaded through envFrom")
    if any(item.get("kind") == "Secret" for item in external_documents):
        raise SystemExit("chart rendered managed Secret with existingSecret configured")

    print("helm check: managed and existing Secret modes valid")


if __name__ == "__main__":
    main()
