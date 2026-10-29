# macOS prerelease publication plan

Prepared locally for review. **Do not run the push or publication commands until the user approves.**
No GitHub draft, tag, asset or branch has been created remotely during preparation.

## Scope

- Repository: `https://github.com/Hongyi-Du/Relic-Plugins.git`
- Release branch: `release/macos-v0.4.1-beta.1`, based on tested upstream commit
  `f995a79e08115e53dbd34f131122075b39c3998a` (`v0.4.1-beta.1`).
- Tag: `v0.4.1-macos-beta.1`; title: **Relic v0.4.1-macos-beta.1 · macOS Apple silicon Beta**.
- Mark as a prerelease, **not latest**. Preserve existing Windows releases and assets.
- Source and live installation stay separate. Do not merge this older runtime branch over upstream main.
- `main-readme.patch` is a separate docs-only change for main; its exact base is recorded in
  `main-readme-base.json`. It adds the Mac download while preserving Windows v0.6 information.

## Local assets and verification

From the clean committed release checkout:

```sh
python3 -B scripts/package.py --platform macos --macos-format both --output dist
cd dist
shasum -a 256 -c SHA256SUMS.txt
```

The release manifest must name the exact release commit with `source_dirty: false`. The
ZIP and tar.gz must have matching logical contents, portable launch templates and no local user paths.
Packaging tests and isolated extracted ZIP installation/start/status/restart/stop are recorded in
the local `test-results` directory. Historical full-suite and live organization evidence is in
`docs/validation.md`; do not represent Windows CI or full browser acceptance as already completed.

## After approval

Create the local annotated tag at the reviewed release commit if it does not already exist, then push
only this release branch and tag. Run the branch's validation workflow before publication and inspect
its result; resolve any failures without rewriting the release tag to a different commit silently.

```sh
git push origin refs/heads/release/macos-v0.4.1-beta.1
git push origin refs/tags/v0.4.1-macos-beta.1
gh release create v0.4.1-macos-beta.1 \
  --repo Hongyi-Du/Relic-Plugins \
  --verify-tag --prerelease --latest=false \
  --title 'Relic v0.4.1-macos-beta.1 · macOS Apple silicon Beta' \
  --notes-file release/v0.4.1-macos-beta.1.md \
  dist/relic-macos-v0.4.1-macos-beta.1.zip \
  dist/relic-macos-v0.4.1-macos-beta.1.tar.gz \
  dist/SHA256SUMS.txt dist/release-manifest.json
```

For the main README update, use a separate checkout of current upstream main. Inspect any upstream
changes since the recorded base before applying `main-readme.patch`; use `git apply --check` first.
Review that only `README.md` and `README.zh-CN.md` change and that the Mac links resolve to the
published tag. Commit that docs-only change and use the repository's normal review/merge process.
Do not replace main with the macOS release branch. Verify both release downloads and their hashes
after publication.
