"""F9: `jura-growth check --file` echoes link excerpts, so a .env full of
webhook URLs comes back to the caller in the issue list. Fake values only."""

import json
from pathlib import Path

from click.testing import CliRunner

from jura_growth.cli import cli


def test_f9_check_file_echoes_secret_urls(tmp_path):
    fake = tmp_path / "fake.env"
    fake.write_text(
        "DISCORD_WEBHOOK_ALERTS=https://discord.com/api/webhooks/111/FAKE-TOKEN-abc\n"
        "RESEND_API_KEY_OUTREACH=re_FAKEKEY123\n"
    )
    out = CliRunner().invoke(cli, ["check", "--file", str(fake), "--json"]).output
    assert "FAKE-TOKEN-abc" in out
    print(out)
