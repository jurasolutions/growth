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
