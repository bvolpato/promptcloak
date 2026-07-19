# Deploy

PromptCloak ships through signed Git tag, GitHub Actions, Homebrew tap, GitHub Pages, and local user service.

## Release

1. Keep same version in `pyproject.toml`, `src/promptcloak/version.py`, Helm chart metadata, Helm image tag, docs, site, and `uv.lock`.
2. Run `AGENTS_TESTING.md` checks.
3. Commit and push release metadata to `main`.
4. Wait for `ci` and `codeql` on pushed commit.
5. Create and push signed tag:

```bash
VERSION=0.1.8
git tag -s "v${VERSION}" -m "PromptCloak ${VERSION}"
git push origin "v${VERSION}"
```

Tag triggers `.github/workflows/release.yml`. Workflow publishes GitHub assets and GHCR image.

## Homebrew

After release assets exist, update `Formula/promptcloak.rb` in
`/home/bruno/githubworkspace/homebrew-tap` with release source URL, checksum, and Python
resources. Reject generated resource versions uploaded less than three days ago; use tested
`uv.lock` version until cooldown expires. Test formula before signed commit and push.

## GitHub Pages

Publish exact contents of `site/` to root of `gh-pages`, commit, and push. Pages source is `gh-pages` branch root.

## Local service

Restart installed source service after release. It listens on `127.0.0.1:8000`:

```bash
systemctl --user restart promptcloak.service
```

OpenCode uses `promptcloak-local` on `127.0.0.1:8787`. Recreate that container from released
GHCR image with loopback binding, `unless-stopped`, raw-request debug off, and configured target
base URL matching OpenCode `X-Target-Base-URL`. Keep upstream key in OpenCode header config; do not
put it in container environment.

Never persist or print upstream credentials during deployment checks.
