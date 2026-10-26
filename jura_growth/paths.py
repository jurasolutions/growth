"""Where things live.

The repo sits at `jurasolutions/repos/growth/`. Data goes to
`jurasolutions/data/growth/`, generated files to `jurasolutions/outputs/growth/`.
Tests point both somewhere temporary with `JURA_GROWTH_DATA_DIR` and
`JURA_GROWTH_OUTPUTS_DIR`.

`inputs/` and `design-system/` are human-maintained and read-only. Every write
helper in this package goes through `writable()`, which refuses them.

Every CLI option or plan field that takes a file path goes through `guard()`,
which keeps secret files away from anything the CLI prints or uploads.
"""

from __future__ import annotations

import fnmatch
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

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
    return Path(os.environ.get("JURA_GROWTH_PROMPTS_DIR", REPO_ROOT / "prompts"))


def pause_file() -> Path:
    return Path(os.environ.get("JURA_GROWTH_PAUSE_FILE", REPO_ROOT / "PAUSE"))


def env_file() -> Path:
    return Path(os.environ.get("JURA_GROWTH_ENV_FILE", REPO_ROOT / ".env"))


def db_path() -> Path:
    return data_dir() / "growth.db"


def work_dir(job: str) -> Path:
    """Scratch space a headless run may write drafts into."""
    return data_dir() / "work" / job


def one_pager_dir() -> Path:
    """The one-pager's grid PNGs, one a day (`grid-YYYY-MM-DD.png`), pruned by the backup."""
    return data_dir() / "one-pager"


class PathRefused(PermissionError):
    """A CLI option or plan field named a file it may not use."""


# File names that hold secrets. The one list: the path guard matches it, and
# headless.secret_read_rules turns it into Claude Code's Read denials.
SECRET_FILE_PATTERNS = (".env*", "*.env", ".dev.vars*")


def is_secret_file(path: str | os.PathLike[str]) -> bool:
    """`.env`, `.env.local`, `prod.env`, `.dev.vars` and the like, in any case
    (macOS folders are case-insensitive, so `.ENV` opens `.env`)."""
    name = Path(path).name.lower()
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in SECRET_FILE_PATTERNS)


def _same_file(a: Path, b: Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:  # either one missing
        return False


def run_folders(job: str) -> list[Path]:
    """The folders a run of `job` may hand to a CLI option or plan field:

    - `data/growth/work/<job>/`, its scratch folder (drafts, plans, leads,
      rendered images);
    - `outputs/growth/`, the engine's own generated files (rendered social
      cards and other images, plans, digests).
    """
    return [work_dir(job), outputs_dir()]


def is_within(path: str | os.PathLike[str], folder: str | os.PathLike[str]) -> bool:
    """Whether `path` is `folder` or sits under it, after resolving both."""
    return Path(path).resolve().is_relative_to(Path(folder).resolve())


# --- the UAT stub (X13) ------------------------------------------------------
#
# `uat.md` points Resend and D1 at a local stub (`uv run python -m tests.resend_stub`)
# through a base-URL variable. Each is honoured only for a loopback http URL while
# the data folder is a temporary one, so a real run can never send through the stub,
# read its empty suppression list, or be fooled into thinking it did.

_LOOPBACK = ("127.0.0.1", "localhost", "::1")


def _temporary(folder: Path) -> bool:
    roots = {Path(tempfile.gettempdir()), Path("/tmp"), Path("/private/tmp"), Path("/private/var/folders")}
    return any(root.exists() and is_within(folder, root.resolve()) for root in roots)


def temporary_data_problem() -> str | None:
    """Why the data folder isn't a temporary one the UAT stub may serve, or None."""
    value = os.environ.get("JURA_GROWTH_DATA_DIR")
    if not value:
        return "JURA_GROWTH_DATA_DIR isn't set: point it at a folder made with `mktemp -d`"
    folder = Path(value).resolve()
    if is_within(folder, JURA_ROOT) or not _temporary(folder):
        return f"the data folder {folder} is not a temporary folder: make one with `mktemp -d`, outside jurasolutions/"
    return None


def stub_url_problem(variable: str) -> str | None:
    """Why the base URL in `variable` may not be used, or None (also None when it is unset)."""
    base = os.environ.get(variable)
    if not base:
        return None
    parts = urlsplit(base)
    if parts.scheme != "http" or parts.hostname not in _LOOPBACK:
        return f"{variable} must point at the local UAT stub (http://127.0.0.1:<port>), not {base}"
    problem = temporary_data_problem()
    return f"{variable} is for the UAT stub only, and {problem}" if problem else None


def guard(path: str | os.PathLike[str]) -> Path:
    """Return `path` resolved, or raise PathRefused.

    Always refused: secret files (see `is_secret_file`), the configured env
    file under any spelling or hard link, and a symlink to either.

    Inside a run (`JURA_GROWTH_JOB` set), only `run_folders(job)` are
    accepted: the job's `data/growth/work/<job>/` scratch folder and
    `outputs/growth/`. Both sit inside jurasolutions/, so this is tighter than
    a `JURA_ROOT` boundary. Outside a run (Ting Yu in Terminal) any other file
    is accepted, as before.
    """
    given = Path(path).expanduser()
    resolved = given.resolve()
    if is_secret_file(given) or is_secret_file(resolved) or _same_file(resolved, env_file().expanduser()):
        raise PathRefused(f"refused: {given} is a secrets file")
    job = os.environ.get("JURA_GROWTH_JOB")
    if job:
        folders = [folder.resolve() for folder in run_folders(job)]
        if not any(is_within(resolved, folder) for folder in folders):
            allowed = " or ".join(str(folder) for folder in folders)
            raise PathRefused(f"refused: a `{job}` run may only use files in {allowed}")
    return resolved


def writable(path: Path) -> Path:
    """Return `path`, creating its parent, unless it sits in a read-only folder."""
    resolved = Path(path).resolve()
    for name in READ_ONLY:
        if is_within(resolved, JURA_ROOT / name):
            raise PermissionError(f"{name}/ is read-only; refusing to write {resolved}")
    if is_within(resolved, inputs_dir()):
        raise PermissionError(f"inputs/ is read-only; refusing to write {resolved}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved
