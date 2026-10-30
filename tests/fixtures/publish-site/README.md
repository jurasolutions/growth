# Publish fixture site (dataset F)

Local pages for Ting Yu's rehearsal of the publish job (test strategy v3 §7, steps R1 to R6). They
imitate the screens a publish run meets: a Page composer with an image upload, a post's permalink,
each stop signal, a membership questions form, a profile-only join screen, a page showing another
identity, a group rules page, a prompt-injection page and a link to `example.org`. Nothing here
loads anything from the network, and no automated test opens these pages in a browser.

Serve them on loopback only, and reach them as `publish-fixture.localhost`:

```bash
uv run python -m http.server 8765 --bind 127.0.0.1 --directory tests/fixtures/publish-site
# then http://publish-fixture.localhost:8765/index.html
```

The composer (`page.html`) keeps a "posted" text in the browser's local storage and opens
`post.html?id=<n>` as its permalink, which shows the live text back.

`index.html` lists which page serves which rehearsal step.

The two join pages are also served at one group's own address, `groups/join/` and
`groups/profile-only-join/`, unchanged: a group item's run may act only inside its own group's
address (`hosts.within`), so `fixture-join` seeds the group there.

The publish job reaches these pages through the fixture platform (BP-07,
`jura_growth/agents/publish/fixture.py`): set `JURA_GROWTH_PUBLISH_FIXTURE_URL` to the server's
address, for example `http://publish-fixture.localhost:8765`, with a temporary data folder. While
it is set, the fixture host is the run's only `ClaudeInChromeDomain` rule, and the publish commands
and the audit accept no other address. The engine accepts only `publish-fixture.localhost` or a
loopback address literal (`127.0.0.1`, `[::1]`), and refuses it with the live data folder.
`uv run python -m tests.uat.seed "$UAT" --scenario fixture-post --page <page>` (or `fixture-join`
for the join pages) seeds an approved item on one page. The steps are in
`.scratch/mission-control/uat.md`, Part R.

`instagram.html` is the same composer as `page.html`, showing the Jura Solutions Instagram account
(`@jura_solutions`), for Instagram's R1, R2 and R6 (`--scenario fixture-post-instagram`; rehearsal 2026-10-30).
