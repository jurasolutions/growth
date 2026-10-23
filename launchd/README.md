# launchd

`jura-growth schedule render` writes one plist per job to `launchd/generated/` (gitignored,
because the plists carry this machine's absolute paths). `jura-growth schedule install` copies
them to `~/Library/LaunchAgents/` as `sg.jurasolutions.growth.<job>.plist` and loads them;
`jura-growth schedule uninstall` unloads and removes them.

The plists are generated from `config/settings.yaml` → `jobs` by `jura_growth/schedule.py`, so
the schedule has one source.
