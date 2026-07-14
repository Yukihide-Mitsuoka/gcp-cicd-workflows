#!/usr/bin/env python3
"""Pin the WIF boundary around the BigQuery cost-gate workflow."""

from pathlib import Path
from typing import Any

import yaml


WORKFLOW = Path(__file__).parents[1] / ".github/workflows/bq-cost-gate.yml"
AUTH_ACTION = "google-github-actions/auth@"
GCLOUD_ACTION = "google-github-actions/setup-gcloud@"
UPLOAD_ACTION = "actions/upload-artifact@"


def fail(message: str) -> None:
    raise AssertionError(message)


def steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    value = job.get("steps", [])
    if not isinstance(value, list):
        fail("job steps must be a list")
    return value


def uses_action(step: dict[str, Any], prefix: str) -> bool:
    value = step.get("uses", "")
    return isinstance(value, str) and value.startswith(prefix)


document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
jobs = document.get("jobs", {})
if not isinstance(jobs, dict):
    fail("workflow jobs must be a mapping")

compile_job = jobs.get("compile")
if not isinstance(compile_job, dict):
    fail("cost gate must have a separate compile job")

gate_job = jobs.get("gate")
if not isinstance(gate_job, dict):
    fail("cost gate must have a separate gate job")

compile_permissions = compile_job.get("permissions", {})
if compile_permissions != {"contents": "read"}:
    fail("compile job must grant only contents: read")

compile_steps = steps(compile_job)
if any(uses_action(step, AUTH_ACTION) for step in compile_steps):
    fail("compile job must not authenticate to Google Cloud")
if any(uses_action(step, GCLOUD_ACTION) for step in compile_steps):
    fail("compile job must not install authenticated cloud tooling")

upload_steps = [step for step in compile_steps if uses_action(step, UPLOAD_ACTION)]
if len(upload_steps) != 1:
    fail("compile job must upload exactly one isolated SQL artifact")
upload_inputs = upload_steps[0].get("with", {})
if not isinstance(upload_inputs, dict) or upload_inputs.get("include-hidden-files") is not True:
    fail("isolated hidden SQL staging tree must be included in the artifact")

gate_permissions = gate_job.get("permissions", {})
if gate_permissions.get("id-token") != "write":
    fail("gate job must grant id-token: write for WIF")
needs = gate_job.get("needs")
if needs != "compile" and not (isinstance(needs, list) and "compile" in needs):
    fail("gate job must depend on the compile artifact")

gate_steps = steps(gate_job)
if not any(uses_action(step, AUTH_ACTION) for step in gate_steps):
    fail("gate job must own Google Cloud authentication")

for job_name, job in jobs.items():
    if not isinstance(job, dict):
        continue
    for step in steps(job):
        command = step.get("run", "")
        if not isinstance(command, str) or "inputs.compile_command" not in command:
            continue
        if job_name != "compile":
            fail("compile_command must execute only in the uncredentialed compile job")

for step in gate_steps:
    command = step.get("run", "")
    if isinstance(command, str) and "inputs.compile_command" in command:
        fail("credentialed gate job must never evaluate compile_command")

print("bq-cost-gate WIF boundary: OK")
