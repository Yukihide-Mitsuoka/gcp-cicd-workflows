# ADR-0001: Isolate cost-gate compilation from WIF credentials

- Status: accepted
- Date: 2026-07-13
- Owner approval: approved in the secure-ga4-bq-template delivery thread

## Context

`bq-cost-gate.yml` accepts a caller-provided `compile_command`. The v1 workflow runs
that command after Workload Identity Federation authentication so compilation can use
Application Default Credentials. A pull request can change the caller workflow, a
referenced script, or a Make target and thereby influence that command. Executing it in
the same job as cloud credentials crosses the untrusted-code boundary and can turn a
cost-estimation workflow into arbitrary credentialed command execution.

The workflow must remain engine-independent, support generated SQL, use keyless
authentication for BigQuery dry runs, and never apply infrastructure or query data.

## Options considered

### Option 1: Keep the single authenticated job

This preserves compatibility and is operationally simple, but leaves caller-controlled
code and cloud credentials in one trust domain. Rejected.

### Option 2: Allowlist compile command text

An allowlist cannot see through scripts, Make targets, package hooks, or modified tool
configuration. It creates a false security boundary and couples the shared workflow to
specific engines. Rejected.

### Option 3: Split compilation and dry run into separate jobs - chosen

Run compilation in a job with `contents: read` and no `id-token` permission. Stage only
regular, non-symlink SQL files beneath the checkout and upload them as an immutable
artifact. A dependent job obtains WIF credentials, downloads that artifact, and performs
only the fixed BigQuery dry-run implementation.

### Option 4: Require committed, precompiled SQL

This is the smallest trusted surface, but generated SQL would need to be committed and
kept synchronized with models. It defeats the existing engine-independent integration
contract. Rejected for now.

## Decision

1. The `compile` job has `contents: read` only and contains no auth or gcloud setup step.
2. `compile_command` remains a caller input, but it executes only in the uncredentialed
   job. Commands that require ADC are no longer supported.
3. The compile job copies matched regular `.sql` files from inside the checkout into a
   fixed staging tree. Symlinks and paths resolving outside the checkout fail closed.
4. The staging tree is uploaded with `actions/upload-artifact@v4`.
5. The `gate` job depends on `compile`, grants `id-token: write`, checks out the reviewed
   budget file, authenticates, downloads the SQL artifact, and runs only fixed local
   dry-run code. It never evaluates `compile_command`.
6. A structural regression test enforces the job and permission boundary in CI.

## Consequences

Positive:

- Caller-controlled compilation cannot access WIF credentials from this workflow.
- The credentialed job has a small, reviewable command surface.
- SQL remains engine-independent and budget overrides retain repository-relative paths.

Negative:

- The workflow uses two runners and an artifact transfer, increasing latency and cost.
- Compile commands that require warehouse metadata via ADC must be redesigned to compile
  offline or use a separately reviewed workflow; this is a breaking v1 contract change.
- Artifact staging adds path-validation code that must be maintained.

## Migration and rollback

Publish the split contract under `v2`. Consumers must make compilation credential-free
and change their caller from `@v1` to `@v2`. Roll back a caller by pinning its previously
reviewed workflow version; do not restore credentialed arbitrary command execution as a
general-purpose path.
