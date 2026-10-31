# n8n workflow: Todoist to inbox

`apc-homelab/workflows/todoist-to-inbox.json` is the whole capture pipeline in n8n.
Import it once; credentials are created by hand in the n8n UI and never go in this repo.

## What it does

Every 5 minutes:

1. Reads open tasks in the **Input Ingestion** Todoist project (`6hv2jrpWj9QgvfR4`).
2. Takes the URL from each task. Both `[title](url)` (iOS share sheet) and a bare URL work.
   Tasks with the `failed` label are skipped.
3. One task at a time, asks the fetcher (`http://127.0.0.1:8080/fetch`) for the note.
4. Writes it to `/inbox/<filename>.md` (the host's `/srv/inputs`).
5. Runs `brain-run` over SSH. That moves the note into `make/Input/Clippings` and has
   Claude fill the summary and tags.
6. Comments on the task and completes it.

If the fetch fails, the task stays open, gets the `failed` label and a comment with the
reason. Remove the label to try again. If only the summary step fails, the note is already
saved and the task is still completed; the hourly `brain-run.timer` retries the summary.

Task text is only ever used to pull out a URL. The fetcher refuses private addresses.

## One-time setup

1. **SSH key.** On the Dell, as `pipeline`: `ssh-keygen -t ed25519 -f ~/n8n_agent_key -N ""`.
   Put the `.pub` line in `n8n_ssh_pubkey` (group_vars) and run the playbook. Paste the private
   key into n8n, then delete the file.
2. **n8n credentials** (Credentials, Add):
   - *Header Auth* named `Todoist API token`: name `Authorization`, value `Bearer <token>`.
     Token from Todoist Settings, Integrations, Developer.
   - *SSH* (private key) named `brain-run on rhel10-dell`: host `host.containers.internal`,
     port 22, user `agent`, the private key.
3. **Import** the JSON (Workflows, Import from file), then open each node that shows a
   credential warning and pick the credentials above.
4. **Test.** Run it manually with one task in the project and watch the executions.
5. **Activate** the workflow.

## Known unknowns

Not run against a live n8n or the Todoist API yet. The node settings follow n8n 2.x and
Todoist API v1 (`api.todoist.com/api/v1`); if import or a call complains, check those first.
