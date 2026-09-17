# Sigma team dispatcher

`sigma-team poll` is a deterministic, one-shot tick. `sigma-team serve` runs the
same tick continuously, once per minute by default, and keeps subprocess workers
in the service cgroup. An empty queue performs no model call. State lives in
`/srv/agents/sigma/team` and is written atomically under `flock`; only one task
can be active globally.

The flow is `Backlog -> running -> sigma_verification -> human_verification`.
The executor must submit its exact Project item to `Sigma verification`; the
engine verifies that transition before it launches the independent reviewer.
Executor failure, adapter error, cancellation, and ambiguous crash go to `Pending`. The engine
never sets `Done` and never retries automatically. A completed or pending issue may be claimed
again only after a newer `/sigma retry` comment by `ai-babai` or `MisterMolox`.
Machine accounts and a repeated move to Backlog do not authorize retry.
After an explicit request from Maks in the trusted Telegram chat, Hermes may run
`sigma-team authorize-retry ISSUE --requested-by 199560169 --reason TEXT`. This
only records one durable authorization. It does not move or start the issue, and
the next eligible Backlog claim consumes it exactly once. The retry resumes the previous
worktree, branch and recorded commit, never a new branch from `main`; a dirty prior worktree
is put in `Pending` rather than being guessed safe. The retry prompt includes the current
title, body, comments and the Telegram authorization reason. No other Telegram ID
is currently accepted. A human GitHub `/sigma retry` remains an alternative.

## Board commands for Hermes

`sigma-task` uses only `/etc/sigma-team/github`, clears token environment
variables, and verifies `aika-ai-agent` before every write. It does not create a
retry authorization.

```text
sigma-task list
sigma-task create --title TITLE --body-file FILE --area BE --initiator Макс --executor 'Команда Sigma' --status Backlog
sigma-task set NUMBER --status 'Human verification'
sigma-task set NUMBER --executor 'Команда Sigma'
sigma-task comment NUMBER --file FILE
```

Create first creates the repository issue, then adds it to Project #2 and fills
the dynamically resolved single-select fields plus the text field `Инициатор`.
If a later step fails, the error
prints the existing issue URL and explicitly tells Hermes not to repeat create.

Pause prevents claims and new reviewer launches. It keeps observing a running
executor or reviewer and does not kill either process.

Hermes-facing controls are `sigma-team control pause|resume|status`. The only
mutable settings are `sigma-team configure default_executor opencode|codex` and
`sigma-team configure poll_interval SECONDS` (bounded to 30..900). `serve` reads
the setting after every tick; the normal deployment value is 60 seconds.

## Adapter contract

The configured Python module (default `adapters`) exports:

* `start_executor(mode, workdir, prompt, run_id) -> dict`
* `executor_status(run_dict) -> dict`
* `start_reviewer(workdir, prompt, run_id) -> dict`
* `reviewer_status(run_dict) -> dict`
* `cancel(run_dict) -> dict`

Starts return immediately with a JSON-serializable dict containing
`external_id`. They must be idempotent by `run_id`. Status returns `state` equal
to `running`, `succeeded`, `failed`, or `blocked`, plus a short `summary` and an
optional `artifact`. A completed reviewer uses `state: succeeded` and reports
its independent `verdict: pass|fail`; both verdicts advance to human verification.
Adapter `failed` or `blocked` means no valid review and advances to Pending.
External sessions must survive the one-shot dispatcher.
`cancel` is called with the exact persisted executor or reviewer run. It returns
`{"confirmed": true, "reason": "..."}` after the worker is known stopped, or a
mapping that explicitly establishes that confirmation. Any other value, exception, or
unconfirmed result leaves the cancellation pending and prevents a next worker launch.

## Durable delivery and cancellation

Before every Project status, GitHub comment, and Telegram notification, the dispatcher writes
a durable outbox event. Events retry with bounded exponential backoff. Comments carry an event
marker; after an uncertain comment timeout, a freshly returned issue comment carrying that
marker is treated as delivered rather than duplicated. A delivery outage after a successful
worker or review retains the active logical phase and worker slot, so it cannot launch again.
The current GitHub adapter exposes comment presence only through the next board poll; this is
the timeout duplicate check available without a second write API.

Record an active cancellation promptly and idempotently:

```text
sigma-team cancel NUMBER --requested-by 199560169 --reason TEXT
```

The next poll handles cancellation before normal status progression, including a reservation,
executor, review wait, reviewer, or completion race. It preserves adapter responses as evidence,
does not launch another worker until confirmed, then delivers `Pending` with the recorded reason.
Before review, the dispatcher reads the fixed commit and associated PR metadata
with its service credential and embeds the snapshot plus observation time in the
review prompt. The read-only reviewer receives no GitHub credential. Evidence
API errors are disclosed in the prompt and never treated as verified state.

The production service runs `sigma-team serve`, so detached Codex/Hermes workers
stay in its cgroup. OpenCode is the primary executor through its asynchronous
HTTP API. Codex is the alternate executor running with normal sigma-ops OS permissions
(`danger-full-access` CLI sandbox mode): workspace-write makes .git read-only
and prevents the required commit/push. This grants no sudo/root permissions. Independent
review is always a Hermes one-shot process inside a bubblewrap mount namespace:
the host filesystem and task worktree are read-only, while only the dedicated
Hermes home and `/tmp` are writable.

Deploy the files under `config/` as follows (they contain no credentials):

* `config/opencode/agents/sigma-worker.md` into the OpenCode agent directory;
* `config/codex/config.toml` as `/home/sigma-ops/.codex-sigma-worker/config.toml`;
* `config/hermes-reviewer/config.yaml` as `/home/sigma-ops/.hermes-reviewer/config.yaml`.

The service environment supplies `OPENAI_API_KEY` and the two
`OPENCODE_SERVER_*` variables from root-owned environment files. Do not copy
secret values into these templates. The service also needs `/usr/bin/bwrap`,
the pinned Codex and Hermes binaries, and read access to the scoped
`/etc/sigma-team/github` configuration.
The engine creates one isolated `/srv/lct/work/team-<issue>-<run>` directory per
attempt from the configured HTTPS source and passes that same directory to the
executor and read-only reviewer. Clone authentication is explicitly routed
through `sigma-gh` before the clone starts. The clone clears inherited credential
helpers, installs a repository-local Sigma helper and Sigma Git author, creates
`sigma/<issue>-<run>` from `repo_ref`, and points `origin` at `repo_remote`.

The notification command receives one JSON object on stdin. Recipient is fixed
in code to Maks Telegram ID `199560169`; the sink owns Telegram credentials.

Example `/etc/sigma-hermes/team.json`:

```json
{
  "state_root": "/srv/agents/sigma/team",
  "work_root": "/srv/lct/work",
  "repo_source": "https://github.com/ai-babai/brutforce.git",
  "repo_ref": "main",
  "repo_remote": "https://github.com/ai-babai/brutforce.git",
  "executor": "opencode",
  "adapter_module": "adapters",
  "notification_command": ["/opt/sigma-hermes/bin/sigma-team-notify"]
}
```

## Private repository access in review

Owner explicitly requested direct private-repository access for Hermes review.
The reviewer uses sigma-gh and the existing aika-ai-agent native credential store,
mounted read-only. Its task filesystem is enforced read-only. GitHub write
prohibition is a reviewer-role instruction: the shared Sigma credential retains
Write/Project permissions required by the coordinator, and is not a read-only
OAuth token. Telegram/OpenCode/STT credentials and normal home remain hidden.
