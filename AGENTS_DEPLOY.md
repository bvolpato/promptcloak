# Deploy

PromptCloak ships through signed Git tag, GitHub Actions, Homebrew tap, GitHub Pages, and local user service.

## Release

1. Keep version aligned in `pyproject.toml`, `src/promptcloak/version.py`, Helm chart metadata, Helm image tag, docs, site, and `uv.lock`.
2. Run `AGENTS_TESTING.md` checks.
3. Commit and push release metadata to `main`.
4. Wait for `ci` and `codeql` on pushed commit.
5. Create and push signed tag:

```bash
VERSION=0.1.7
git tag -s "v${VERSION}" -m "PromptCloak ${VERSION}"
git push origin "v${VERSION}"
```

Tag triggers `.github/workflows/release.yml`. Workflow publishes GitHub assets and GHCR image.

## Homebrew

After release assets exist, update `Formula/promptcloak.rb` in `/home/bruno/githubworkspace/homebrew-tap` with release source URL, checksum, and Python resources. Test formula before signed commit and push.

## GitHub Pages

Publish exact contents of `site/` to root of `gh-pages`, commit, and push. Pages source is `gh-pages` branch root.

## Local service

Restart installed user service after release:

```bash
systemctl --user restart promptcloak.service
```

Never persist or print upstream credentials during deployment checks.
