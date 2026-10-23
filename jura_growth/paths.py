"""Where things live.

The repo sits at `jurasolutions/repos/growth/`. Data goes to
`jurasolutions/data/growth/`, generated files to `jurasolutions/outputs/growth/`.
Tests point both somewhere temporary with `JURA_GROWTH_DATA_DIR` and
`JURA_GROWTH_OUTPUTS_DIR`.

`inputs/` and `design-system/` are human-maintained and read-only. Every write
helper in this package goes through `writable()`, which refuses them.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
JURA_ROOT = Path(os.environ.get("JURA_ROOT", REPO_ROOT.parent.parent)).resolve()

READ_ONLY = ("inputs", "design-system")


def data_dir() -> Path:
    return Path(os.environ.get("JURA_GROWTH_DATA_DIR", JURA_ROOT / "data" / "growth"))


def outputs_dir() -> Path:
    return Path(os.environ.get("JURA_GROWTH_OUTPUTS_DIR", JURA_ROOT / "outputs" / "growth"))


def inputs_dir() -> Path:
    return Path(os.environ.get("JURA_INPUTS_DIR", JURA_ROOT / "inputs"))


def prd_dir() -> Path:
    return Path(os.environ.get("JURA_PRD_DIR", JURA_ROOT / "prd"))


def site_repo() -> Path:
    return Path(os.environ.get("JURA_SITE_REPO", JURA_ROOT / "repos" / "landing-page"))


def config_dir() -> Path:
    return Path(os.environ.get("JURA_GROWTH_CONFIG_DIR", REPO_ROOT / "config"))


def prompts_dir() -> Path:
    return REPO_ROOT / "prompts"


def pause_file() -> Path:
    return Path(os.environ.get("JURA_GROWTH_PAUSE_FILE", REPO_ROOT / "PAUSE"))


def env_file() -> Path:
    return Path(os.environ.get("JURA_GROWTH_ENV_FILE", REPO_ROOT / ".env"))


def db_path() -> Path:
    return data_dir() / "growth.db"


def work_dir(job: str) -> Path:
    """Scratch space a headless run may write drafts into."""
    return data_dir() / "work" / job


def writable(path: Path) -> Path:
    """Return `path`, creating its parent, unless it sits in a read-only folder."""
    resolved = Path(path).resolve()
    for name in READ_ONLY:
        guarded = (JURA_ROOT / name).resolve()
        if resolved == guarded or guarded in resolved.parents:
            raise PermissionError(f"{name}/ is read-only; refusing to write {resolved}")
    if inputs_dir().resolve() in resolved.parents:
        raise PermissionError(f"inputs/ is read-only; refusing to write {resolved}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved
