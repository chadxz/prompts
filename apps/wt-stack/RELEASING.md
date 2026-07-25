# Releasing wt-stack

This is the required process for publishing `wt-stack`. Follow it in order.
Don't move or reuse a tag after pushing it.

## Expected outcome

A successful release creates a non-draft, non-prerelease GitHub Release from an
annotated `wt-stack/v<major>.<minor>.<patch>` tag on `main`. The release
contains:

- Four archives named
  `wt-stack_<version>_<operating-system>_<architecture>.tar.gz` for macOS and
  Linux on amd64 and arm64.
- `README.md`, `LICENSE`, `CHANGELOG.md`, and the `wt-stack` binary in each
  archive.
- `checksums.txt` and its keyless Cosign signature bundle.
- One SPDX JSON SBOM for each archive.
- GitHub build-provenance attestations for every archive, the checksum file, and
  every SBOM.

The binary must print the released version with `wt-stack --version`. GitHub
must mark both release jobs successful before we consider the release complete.

Only `wt-stack/v*` tags start this app's release workflow.

## 1. Choose the version

Use Semantic Versioning:

- Increment the major version for an incompatible CLI, state, or JSON contract
  change.
- Increment the minor version for backward-compatible commands or behavior.
- Increment the patch version for backward-compatible fixes.

Use the version once. If any pushed tag or published release uses it, choose a
newer version for the next attempt.

## 2. Prepare the changelog

Start from a clean worktree whose `HEAD` matches `origin/main`:

```console
git fetch origin main --tags
git status --short
git rev-parse HEAD
git rev-parse origin/main
```

Stop if the status output isn't empty or the two commit IDs differ.

Move every completed entry under `Unreleased` into a dated version section:

```markdown
## Unreleased

## 1.2.3 - 2026-07-24
```

Use the release version and current local date. Leave `Unreleased` in place for
the next change. Commit the changelog and any release documentation before
tagging.

## 3. Validate the release commit

Install the pinned tools and run the deterministic local checks:

```console
mise -C apps/wt-stack install
mise run //apps/wt-stack:format-check ::: \
  //apps/wt-stack:lint ::: \
  //apps/wt-stack:test ::: \
  //apps/wt-stack:vet ::: \
  //apps/wt-stack:tidy-check ::: \
  //apps/wt-stack:verify ::: \
  //apps/wt-stack:release-check ::: \
  //apps/wt-stack:build
mise run //apps/wt-stack:test-integration
GORELEASER_CURRENT_TAG=v1.2.3 WT_STACK_SKIP_CHANGELOG=true \
  mise -C apps/wt-stack exec -- \
  goreleaser release --clean --skip=publish,sign,sbom,validate
```

The unit suite must meet the coverage minimum without the integration build tag.
The integration suite must pass separately. The local package check must build
all four target archives with the intended version. Replace `v1.2.3` with the
chosen version.

GoReleaser validation is skipped only because its OSS release path requires an
unprefixed Git tag. The release workflow separately requires a
`wt-stack/v<version>` tag and verifies that it identifies the checked-out commit
before building.

Push the release-preparation commit to `main`, then wait for `wt-stack CI` on
that exact commit:

```console
git push origin HEAD:main
gh run list --workflow wt-stack-ci.yml --branch main --limit 1
gh run watch <run-id> --exit-status
```

GitHub CI is the authoritative release gate. It reruns the local checks and the
pinned vulnerability scan on Linux and macOS. Stop if either job doesn't
succeed. Fix the problem in a new commit, push it, and repeat this section.

## 4. Create and push the tag

Confirm `HEAD` still matches `origin/main`. Replace `1.2.3` in these commands
with the chosen version:

```console
git fetch origin main
git rev-parse HEAD
git rev-parse origin/main
git tag -a wt-stack/v1.2.3 -m "wt-stack v1.2.3"
git push origin wt-stack/v1.2.3
```

Stop before tagging if the commit IDs differ. Don't force a tag push.

The tag starts `wt-stack release`. Its validation job reruns the full required
suite. The release job runs only after validation succeeds:

```console
gh run list --workflow wt-stack-release.yml --limit 1
gh run watch <run-id> --exit-status
```

## 5. Verify the published release

Inspect the release and download its assets into a new temporary directory:

```console
gh release view wt-stack/v1.2.3
mkdir /tmp/wt-stack-v1.2.3
gh release download wt-stack/v1.2.3 --dir /tmp/wt-stack-v1.2.3
cd /tmp/wt-stack-v1.2.3
```

Confirm that all four archives, four SBOMs, the checksum, and signature bundle
exist. Verify the archive checksums:

```console
shasum -a 256 -c checksums.txt
```

Verify the keyless signature. The certificate identity must match the release
workflow at the release tag:

```console
certificate_identity="https://github.com/chadxz/prompts/.github/workflows/\
wt-stack-release.yml@refs/tags/wt-stack/v1.2.3"
cosign verify-blob \
  --bundle checksums.txt.sigstore.json \
  --certificate-identity "$certificate_identity" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  checksums.txt
```

Verify provenance for each archive, checksum file, and SBOM:

```console
gh attestation verify <asset> --repo chadxz/prompts
```

Inspect each SBOM as SPDX JSON:

```console
jq -e '.spdxVersion' *.sbom.json
```

Extract the archive for the current machine and confirm the embedded version:

```console
tar -xzf wt-stack_1.2.3_darwin_arm64.tar.gz
./wt-stack --version
```

The command must print `wt-stack version 1.2.3`. Use the archive matching the
verification machine.

## 6. Handle a failed release

If failure occurs before the tag is pushed, fix the release commit and repeat
validation.

If failure occurs after the tag is pushed, treat that version as consumed. Don't
move the tag, delete and recreate it, or overwrite its release assets. Fix the
problem on `main`, move the changelog entries to the next patch version, and
repeat this process with the new version.

If verification finds a bad artifact after publication, preserve the release for
traceability and publish a corrected patch release. Record the correction in
`CHANGELOG.md`.
