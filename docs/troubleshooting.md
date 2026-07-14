# Troubleshooting — error-pattern playbook

For the AI (or human) reading a failed run log. Headings are the verbatim error text where
one exists — search for the message you see. Each entry: cause → check → fix.

## `Error: ... failed to generate Google Cloud federated token ... (unauthorized)`

**Cause:** the OIDC token's claims don't satisfy the provider's `attribute_condition`.
**Check:**
1. Is the calling repo exactly the module's `github_repository` (owner/name, case-sensitive)?
2. Was the condition tightened to a branch (`assertion.ref`) and this run is from a PR/other branch?
3. Does the caller job have `permissions: id-token: write`? (Without it the token is never minted — the error appears as a missing/invalid token.)
**Fix:** align `github_repository` / `attribute_condition` in the terraform module with where the workflow actually runs; re-apply; re-run.

## `Error: ... iam.serviceAccounts.getAccessToken denied`

**Cause:** federated identity may not impersonate the service account.
**Check:** the SA's IAM policy contains `roles/iam.workloadIdentityUser` for `principalSet://...attribute.repository/<owner/name>` (the module creates this — was the module's output SA the one passed to the workflow?).
**Fix:** pass the module outputs verbatim (`WIF_PROVIDER`, `DEPLOYER_SA` repo variables); if hand-edited, re-apply the module.

## `Error acquiring the state lock`

**Cause:** another plan/apply holds the GCS state lock (parallel PR runs, or a killed run left a stale lock).
**Check:** `gcloud storage ls gs://<state-bucket>/<prefix>/` for a `.tflock`; look for a concurrently running workflow.
**Fix:** wait for the other run; for a confirmed-stale lock: `terraform force-unlock <ID>` (needs human approval — GR-031-class action). Prevention: `concurrency:` group per env in the caller.

## `denied: Permission "artifactregistry.repositories.uploadArtifacts" denied`

**Cause:** deployer SA lacks `roles/artifactregistry.writer`, or image path targets the wrong project/repo.
**Check:** module `roles` input; the `image` input's project id and repo name exist.
**Fix:** add the role to the module's `roles` list and apply.

## Plan comment never appears on the PR

**Cause:** caller forgot `permissions: pull-requests: write`, or the event is not `pull_request` (comments are skipped on push).
**Fix:** set the permission in the CALLER workflow (reusable workflows can't raise the caller's grant).

## `Health check failed at N% — rolling back`

**Cause:** the canary revision fails its health endpoint under real traffic.
**Check:** Cloud Run logs for the NEW revision only (`resource.labels.revision_name=<new>`); diff env vars/secrets between revisions; migration mismatch (deployed code expects a schema the migrate step didn't apply?).
**Fix:** traffic already rolled back automatically — fix the defect, ship a new PR. Do not re-run the failed deploy job.

## Migration job fails / `Job execution ... failed`

**Cause:** migration error (SQL failure, connectivity, missing permissions on Cloud SQL).
**Check:** `gcloud run jobs executions describe` + logs; if `rollback_args` was set, verify the rollback execution succeeded (a failed rollback = stop everything, restore from backup per your runbook).
**Fix:** repair the migration; remember deploy never ran (migrate is `needs:` upstream of deploy), so serving traffic is still on the old code.

## `Error: Resource ... jobs.run.invocations` / deploy times out waiting

**Cause:** Cloud Run job/service stuck pulling image (wrong region registry, digest not pushed) or startup probe failing.
**Check:** the image ref is the digest output of container-build (not a tag that was never pushed — PR builds use `push: false`); region of Artifact Registry matches.
**Fix:** ensure CD calls container-build with `push: true` and passes `needs.build.outputs.image` (digest-pinned).

## `Error: workflow was not found` when calling a floating major

**Cause:** consumer repo cannot see this repo (private) or the tag doesn't exist yet.
**Fix:** this repo is public — check the path spelling and that the workflow's documented
major (`v1` or `v2`) exists with `git ls-remote --tags`.

## `no SQL files match ... (did compile_command run?)`

**Cause:** the v2 cost-gate compile job did not produce files matching `sql_glob`, or
the command failed because it expected ADC. Compilation intentionally has no cloud
credentials (ADR-0001).
**Check:** run the exact `compile_command` in a credential-free clean checkout and inspect
the generated paths.
**Fix:** make compilation offline and update `sql_glob`. Do not move authentication back
into compilation and do not pass `DEPLOYER_SA`.

## `No files were found with the provided path: .bq-cost-gate-input/`

**Cause:** `actions/upload-artifact` excluded the hidden SQL staging directory. This was
fixed in the reusable workflow after v2.0.0.
**Fix:** upgrade the reusable cost-gate workflow to the latest v2 release.

## `dry-run error ... WARNING: --scopes flag may not work as expected`

**Cause:** older cost-gate releases treated the WIF external-account warning around a
successful `bq --format=json` response as malformed JSON.
**Fix:** upgrade the reusable cost-gate workflow to the latest v2 release.

## `budget override ... needs a non-empty reason`

**Cause:** a per-path budget exception lacks its required audit rationale.
**Fix:** add a concise `reason` explaining why the larger scan is accepted, or remove the
override and reduce the model's estimated bytes.

## Rules for the responding AI

- Read the failing step's log first; match a heading here before proposing changes.
- Auth errors are almost always terraform-side (module inputs), not workflow-side — fix in
  the consumer's `infra/`, not by editing the reusable workflow.
- Never work around a failed gate (approval, health check, migration) by re-running with
  altered inputs; fix the cause (GR-012 spirit).
