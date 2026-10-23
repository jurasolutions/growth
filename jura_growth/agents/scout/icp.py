"""The ICP (`inputs/icp.md`, Ting Yu's file) and today's industry rotation.

The scout reads the ICP and never writes it. Block 1 leaves a draft at
`outputs/growth/setup/icp-draft.md` for Ting Yu to edit and move into
`inputs/` himself.

Industries rotate by business day: the bullets under the ICP's "Industries"
heading if it has one, otherwise `research.industries` in config/scout.yaml.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from jura_growth import holidays, paths, timeutil
from jura_growth.agents.scout import settings

ROTATION_EPOCH = date(2026, 1, 1)


def path() -> Path:
    return paths.inputs_dir() / "icp.md"


def draft_path() -> Path:
    return paths.outputs_dir() / "setup" / "icp-draft.md"


def missing_reason() -> str | None:
    if path().exists():
        return None
    return (
        f"{path()} is missing. Edit the draft at {draft_path()} and move it to inputs/icp.md "
        "(the scout never writes inputs/)"
    )


def industries_from_icp(text: str) -> list[str]:
    """Bullets under a heading that starts with "Industries"."""
    found: list[str] = []
    in_section = False
    for line in text.splitlines():
        heading = re.match(r"^\s{0,3}#{1,6}\s+(.*)$", line)
        if heading:
            in_section = heading.group(1).strip().lower().startswith("industries")
            continue
        if not in_section:
            continue
        bullet = re.match(r"^\s*[-*]\s+(.+)$", line)
        if bullet:
            name = re.split(r"\s+[—–-]\s+|:\s", bullet.group(1).strip(), maxsplit=1)[0]
            name = name.strip().strip("*_").strip()
            if name:
                found.append(name)
    return found


def industries() -> list[str]:
    if path().exists():
        listed = industries_from_icp(path().read_text(encoding="utf-8"))
        if listed:
            return listed
    return list(settings.get()["research"].get("industries") or [])


def todays_industries(day: date | None = None) -> list[str]:
    """1–2 industries for `day`, rotating through the list by business day."""
    names = industries()
    if not names:
        return []
    day = day or timeutil.today()
    per_day = max(1, min(int(settings.get()["research"].get("industries_per_day") or 2), 2, len(names)))
    index = holidays.business_days_between(ROTATION_EPOCH, day) if day > ROTATION_EPOCH else 0
    start = (index * per_day) % len(names)
    return [names[(start + offset) % len(names)] for offset in range(per_day)]
