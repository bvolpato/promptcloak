#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import os
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
TAG = re.compile(r"^v(?P<version>\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)$")


def read_pyproject_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def read_package_version() -> str:
    text = (ROOT / "src" / "promptcloak" / "version.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__ = "([^"]+)"$', text, re.MULTILINE)
    if not match:
        raise ValueError("src/promptcloak/version.py missing __version__")
    return match.group(1)


def read_chart_value(name: str) -> str:
    text = (ROOT / "charts" / "promptcloak" / "Chart.yaml").read_text(encoding="utf-8")
    match = re.search(rf"^{name}:\s*\"?([^\"\n]+)\"?$", text, re.MULTILINE)
    if not match:
        raise ValueError(f"charts/promptcloak/Chart.yaml missing {name}")
    return match.group(1)


def tag_version(tag: str | None) -> str | None:
    if not tag:
        return None
    match = TAG.fullmatch(tag)
    if not match:
        raise ValueError(f"release tag must look like v0.1.0, got {tag!r}")
    return match.group("version")


def github_tag() -> str | None:
    if os.getenv("GITHUB_REF_TYPE") != "tag":
        return None
    return os.getenv("GITHUB_REF_NAME")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate release version metadata.")
    parser.add_argument("--tag", default=github_tag())
    args = parser.parse_args()

    expected = tag_version(args.tag) or read_pyproject_version()
    versions = {
        "pyproject.toml": read_pyproject_version(),
        "src/promptcloak/version.py": read_package_version(),
        "charts/promptcloak/Chart.yaml version": read_chart_value("version"),
        "charts/promptcloak/Chart.yaml appVersion": read_chart_value("appVersion"),
    }

    if not SEMVER.fullmatch(expected):
        raise SystemExit(f"invalid version: {expected}")

    mismatches = [
        f"{source}={version}" for source, version in versions.items() if version != expected
    ]
    if mismatches:
        raise SystemExit("release version mismatch: " + ", ".join(mismatches))

    print(f"release check: {expected}")


if __name__ == "__main__":
    main()
