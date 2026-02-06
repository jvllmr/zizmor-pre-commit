# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "packaging",
#     "urllib3",
# ]
# ///

import re
import subprocess
import tomllib
import typing
from pathlib import Path

import urllib3
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version

PACKAGE = "zizmor"


class Release(typing.NamedTuple):
    version: Version
    requires_python: SpecifierSet


def main():
    with open(Path(__file__).parent / "pyproject.toml", "rb") as f:
        pyproject = tomllib.load(f)

    all_releases = get_all_versions()
    current_version = get_current_version(pyproject=pyproject)
    target_releases = [r for r in all_releases if r.version > current_version]

    for release in target_releases:
        paths = process_release(release)
        if subprocess.check_output(["git", "status", "-s"]).strip():
            subprocess.run(["git", "add", *paths], check=True)
            subprocess.run(
                ["git", "commit", "-m", f"Mirror: {release.version}"], check=True
            )
            subprocess.run(["git", "tag", f"v{release.version}"], check=True)
        else:
            print(f"No change v{release}")


def get_all_versions() -> list[Release]:
    response = urllib3.request("GET", f"https://pypi.org/pypi/{PACKAGE}/json")
    if response.status != 200:
        raise RuntimeError("Failed to fetch releases from pypi")

    releases: list[Release] = []
    for v, release_files in response.json()["releases"].items():
        version = Version(v)

        if version.is_prerelease:
            continue

        requires_python = SpecifierSet(">=3.10")
        for f in release_files:
            if f["python_version"] == "py3" and (spec := f["requires_python"]):
                requires_python = SpecifierSet(spec)
                break

        releases.append(Release(version=version, requires_python=requires_python))

    return sorted(releases, key=lambda r: r.version)


def get_current_version(pyproject: dict) -> Version:
    requirements = [Requirement(d) for d in pyproject["project"]["dependencies"]]
    requirement = next((r for r in requirements if r.name == PACKAGE), None)
    assert requirement is not None, (
        f"pyproject.toml does not have {PACKAGE} requirement"
    )

    specifiers = list(requirement.specifier)
    assert len(specifiers) == 1 and specifiers[0].operator == "==", (
        f"{PACKAGE}'s specifier should be exact matching, but `{requirement}`"
    )

    return Version(specifiers[0].version)


def process_release(release: Release) -> typing.Sequence[str]:
    def replace_pyproject_toml(content: str) -> str:
        replaced_version = re.sub(
            rf'"{PACKAGE}==.*"', f'"{PACKAGE}=={release.version}"', content
        )
        return re.sub(
            r'requires-python = ".*"',
            f'requires-python = "{release.requires_python}"',
            replaced_version,
        )

    def replace_readme_md(content: str) -> str:
        content = re.sub(r"rev: v\d+\.\d+\.\d+", f"rev: v{release.version}", content)
        return re.sub(
            rf"/{PACKAGE}/\d+\.\d+\.\d+\.svg",
            f"/{PACKAGE}/{release.version}.svg",
            content,
        )

    paths = {
        "pyproject.toml": replace_pyproject_toml,
        "README.md": replace_readme_md,
    }

    for path, replacer in paths.items():
        with open(path) as f:
            content = replacer(f.read())
        with open(path, mode="w") as f:
            f.write(content)

    return tuple(paths.keys())


if __name__ == "__main__":
    main()
