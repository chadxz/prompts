# Releasing wt-stack

`wt-stack` releases automatically after its required CI succeeds on `main`.
Don't create or push release tags manually.

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

The binary must print the released version with `wt-stack --version`. The
preparation workflow waits for the tagged workflow, so both runs must succeed
before GitHub considers the automatic release complete.

## Release trigger

Every change intended for release must have an entry under `Unreleased` in
`CHANGELOG.md`. Use the standard headings:

- `Breaking changes` or `Removed` for an incompatible change.
- `Added` for backward-compatible functionality.
- `Changed`, `Fixed`, or `Security` for backward-compatible corrections.

After `wt-stack CI` succeeds for a push to `main`, `wt-stack release` examines
the `Unreleased` section. An empty section ends the workflow without creating a
release.

The version is selected without input:

- `Breaking changes` or `Removed` increments the major version.
- `Added` increments the minor version.
- Every other non-empty release increments the patch version.

The workflow uses the latest `wt-stack/v*` tag as the current version. It dates
the release in the `America/Chicago` timezone.

## Automated process

The preparation job performs these steps in order:

1. Confirm the successful CI commit still matches `origin/main`. A newer main
   commit ends the stale run because that commit's CI will trigger another one.
2. Promote `Unreleased` into a dated version section.
3. Run the complete `mise //apps/wt-stack:ci` gate against the prepared
   changelog.
4. Commit the changelog with the GitHub Actions bot and create the annotated
   app-qualified tag.
5. Push the commit and tag atomically. Neither ref moves if the remote rejects
   either update.
6. Dispatch this workflow again at the immutable tag.
7. Wait for the tagged validation, packaging, signing, publication, and
   provenance jobs to finish.

The tagged workflow independently verifies that the tag identifies its checked
out commit before it builds anything.

## Manual recovery trigger

Normal releases require no maintainer action. Use a manual dispatch from `main`
only when an automatic preparation run was skipped or interrupted before its
atomic push:

```console
gh workflow run wt-stack-release.yml --ref main
```

The same version selection and validation rules apply. The workflow exits
without changes when `Unreleased` is empty.

If the preparation job pushed a tag and failed before the tagged workflow
started, dispatch the immutable tag directly:

```console
gh workflow run wt-stack-release.yml --ref wt-stack/v1.2.3
```

Retry the same tag only for an interruption or transient infrastructure error.
Source, configuration, or artifact defects require a fix on `main` and a new
version. Never move, delete, recreate, or force-push a release tag.

## Verify a release

The workflow performs publication checks. For an independent consumer-side
verification, inspect the release and download its assets into a new temporary
directory:

```console
gh release view wt-stack/v1.2.3
release_dir="$(mktemp -d /tmp/wt-stack-v1.2.3.XXXXXX)"
gh release download wt-stack/v1.2.3 --dir "$release_dir"
cd "$release_dir"
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

## Failed or incorrect releases

If failure occurs before the atomic commit and tag push, fix `main` or manually
rerun the preparation workflow. No version has been consumed.

If failure occurs after the tag is pushed, preserve that tag. Retry its workflow
only when the tagged source is correct and publication was interrupted. Any fix
to source or release configuration requires a newer version.

If verification finds a bad artifact after publication, preserve the release for
traceability. Record the correction under `Unreleased` and let the automation
publish the next version.
