# Security policy

## Supported versions

Security fixes are released for the latest `wt-stack` minor version. Upgrade to
the newest release before reporting an issue that may already be fixed.

## Reporting a vulnerability

Use GitHub private vulnerability reporting:

https://github.com/chadxz/prompts/security/advisories/new

Report vulnerabilities involving credentials, unsafe Git operations, path
handling, remote validation, state corruption, or lease bypasses. Do not open a
public issue with exploit details or credentials.

Include the `wt-stack` version, operating system, Git version, remote URL with
credentials removed, reproduction steps, impact, and any proposed mitigation.
You should receive an acknowledgement through GitHub within seven days.

## Security boundaries

`wt-stack` executes Git directly without a shell, validates GitHub API hosts
before attaching credentials, bounds HTTP responses, uses explicit request
timeouts, and stores local state with user-only permissions. It never prints or
persists GitHub tokens.

`WT_STACK_GIT_BIN` is a test and diagnostic override that selects the executable
used for Git operations. Treat it like `PATH`: set it only to trusted code.
