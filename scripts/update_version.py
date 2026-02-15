#!/usr/bin/env python3
"""Version management helper for VirtualCom.

Source of truth:
  - pyproject.toml ([project].version + [tool.virtualcom].release_date)

Derived files:
  - version_info.py
  - installer.iss
  - README.md (line: "Текущая версия")
"""

from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit("Python 3.11+ required (tomllib is missing).") from exc


ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
VERSION_INFO = ROOT / "version_info.py"
INSTALLER_ISS = ROOT / "installer.iss"
README = ROOT / "README.md"

SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def today_ru() -> str:
    return dt.date.today().strftime("%d.%m.%Y")


def read_pyproject() -> tuple[str, str]:
    data = tomllib.loads(read_text(PYPROJECT))
    version = data["project"]["version"]
    release_date = data.get("tool", {}).get("virtualcom", {}).get("release_date", "")
    return version, release_date


def update_pyproject(version: str, release_date: str) -> None:
    content = read_text(PYPROJECT)
    content_new = re.sub(
        r'(?m)^version\s*=\s*"[^"]+"',
        f'version = "{version}"',
        content,
        count=1,
    )
    if content_new == content:
        raise RuntimeError("Could not update version in pyproject.toml")

    if re.search(r'(?m)^release_date\s*=\s*"[^"]+"', content_new):
        content_new = re.sub(
            r'(?m)^release_date\s*=\s*"[^"]+"',
            f'release_date = "{release_date}"',
            content_new,
            count=1,
        )
    elif "[tool.virtualcom]" in content_new:
        content_new = content_new.replace(
            "[tool.virtualcom]",
            f'[tool.virtualcom]\nrelease_date = "{release_date}"',
            1,
        )
    else:
        content_new = content_new.rstrip() + f'\n\n[tool.virtualcom]\nrelease_date = "{release_date}"\n'

    write_text(PYPROJECT, content_new)


def sync_derived(version: str, release_date: str) -> None:
    version_info_content = (
        '"""Derived version data for runtime usage.\n\n'
        "This file is synchronized from pyproject.toml by scripts/update_version.py.\n"
        '"""\n\n'
        f'__version__ = "{version}"\n'
        f'__release_date__ = "{release_date}"\n'
    )
    write_text(VERSION_INFO, version_info_content)

    iss = read_text(INSTALLER_ISS)
    iss_new = re.sub(
        r'(?m)^#define\s+MyAppVersion\s+"[^"]+"',
        f'#define MyAppVersion "{version}"',
        iss,
        count=1,
    )
    write_text(INSTALLER_ISS, iss_new)

    readme = read_text(README)
    version_line = f"**Текущая версия:** `{version}` (релиз: `{release_date}`)"
    if re.search(r"(?m)^\*\*Текущая версия:\*\* .+$", readme):
        readme_new = re.sub(r"(?m)^\*\*Текущая версия:\*\* .+$", version_line, readme, count=1)
    else:
        readme_new = readme.replace("## Описание\n\n", f"## Описание\n\n{version_line}\n\n", 1)
    write_text(README, readme_new)


def bump_version(version: str, level: str) -> str:
    m = SEMVER_RE.match(version)
    if not m:
        raise ValueError(f"Invalid semantic version: {version}")
    major, minor, patch = map(int, m.groups())
    if level == "patch":
        patch += 1
    elif level == "minor":
        minor += 1
        patch = 0
    elif level == "major":
        major += 1
        minor = 0
        patch = 0
    else:
        raise ValueError("level must be patch|minor|major")
    return f"{major}.{minor}.{patch}"


def file_version_status(label: str, value: str, expected: str) -> str:
    mark = "OK" if value == expected else "MISMATCH"
    return f"{label:<20} {value:<20} [{mark}]"


def status() -> int:
    version, release_date = read_pyproject()
    print(f"pyproject version     : {version}")
    print(f"pyproject release_date: {release_date}")

    vi = read_text(VERSION_INFO)
    vi_ver = re.search(r'__version__\s*=\s*"([^"]+)"', vi)
    vi_date = re.search(r'__release_date__\s*=\s*"([^"]+)"', vi)
    vi_ver_v = vi_ver.group(1) if vi_ver else "N/A"
    vi_date_v = vi_date.group(1) if vi_date else "N/A"

    iss = read_text(INSTALLER_ISS)
    iss_ver = re.search(r'(?m)^#define\s+MyAppVersion\s+"([^"]+)"', iss)
    iss_ver_v = iss_ver.group(1) if iss_ver else "N/A"

    readme = read_text(README)
    rd = re.search(r"(?m)^\*\*Текущая версия:\*\* `([^`]+)` \(релиз: `([^`]+)`\)", readme)
    rd_ver_v = rd.group(1) if rd else "N/A"
    rd_date_v = rd.group(2) if rd else "N/A"

    print()
    print(file_version_status("version_info.py", vi_ver_v, version))
    print(file_version_status("version_info date", vi_date_v, release_date))
    print(file_version_status("installer.iss", iss_ver_v, version))
    print(file_version_status("README version", rd_ver_v, version))
    print(file_version_status("README date", rd_date_v, release_date))
    return 0


def sync(version_arg: str | None) -> int:
    curr_version, _curr_date = read_pyproject()
    target_version = version_arg or curr_version
    if not SEMVER_RE.match(target_version):
        raise SystemExit(f"Invalid VERSION: {target_version}")
    release_date = today_ru()
    update_pyproject(target_version, release_date)
    sync_derived(target_version, release_date)
    print(f"Synchronized version: {target_version} (release_date: {release_date})")
    return 0


def release(version_arg: str | None) -> int:
    # Safe default: only sync. Git actions remain explicit user choice.
    sync(version_arg)
    print("Release files synchronized. Commit/push manually if needed.")
    return 0


def usage() -> int:
    print(
        "Usage:\n"
        "  python3 scripts/update_version.py status\n"
        "  python3 scripts/update_version.py sync [VERSION]\n"
        "  python3 scripts/update_version.py bump patch|minor|major\n"
        "  python3 scripts/update_version.py release [VERSION]\n"
    )
    return 1


def main() -> int:
    if len(sys.argv) < 2:
        return usage()

    cmd = sys.argv[1]
    if cmd == "status":
        return status()
    if cmd == "sync":
        version_arg = sys.argv[2] if len(sys.argv) > 2 else None
        return sync(version_arg)
    if cmd == "bump":
        if len(sys.argv) < 3:
            return usage()
        level = sys.argv[2]
        current_version, _ = read_pyproject()
        next_version = bump_version(current_version, level)
        return sync(next_version)
    if cmd == "release":
        version_arg = sys.argv[2] if len(sys.argv) > 2 else None
        return release(version_arg)

    return usage()


if __name__ == "__main__":
    raise SystemExit(main())
