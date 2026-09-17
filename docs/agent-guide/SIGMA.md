# GitHub identity for Sigma

Designated identity: **aika-ai-agent**, GitHub numeric ID330356150.
Repository: https://github.com/ai-babai/brutforce
Project: https://github.com/users/ai-babai/projects/2
GitHub permissions verified: repository Write, Project Writer. Service token expires 2026-12-16; scopes repo + project. Server acceptance is tracked in infra-os runs.

## Mandatory identity

Any agent working **on behalf of Sigma** uses aika-ai-agent for GitHub API, issues, comments, Project fields, PRs and Git push. Do not use ai-babai, MisterMolox, their personal tokens, or the shared lct repository deploy key as Sigma's authentication.
Humans' local agents doing their own work can continue using their own accounts. Do not overwrite their Git configuration or credentials.

Before GitHub writes run `gh api user --jq .login` and verify exact `aika-ai-agent`. If token absent, expired, wrong identity or missing permission: stop GitHub writes and report the blocker. Never fall back to another account. Do not print environment, tokens or credential-helper output. Do not run `gh auth login` with a human account on this server.

## Runtime

Hermes runs as Linux user sigma-ops (not lct). Systemd loads GH_TOKEN from root-owned /etc/sigma-hermes/github.env into gateway and board runner; subprocesses inherit it. Token must not appear in repository URLs, command arguments, logs or onboarding archives. Use gh for API/PR operations and HTTPS Git with gh credential helper. No token stored in Git config.

Git author: aika-ai-agent <330356150+aika-ai-agent@users.noreply.github.com>. Commit attribution alone is not authentication; verify API identity as above.
Use own clone/worktree and codex/sigma-<task> branch. Shared /srv/lct/repo uses another deploy credential; do not change its remote/config or write into other people's worktrees. Prefer a separate clone under /srv/lct/work/sigma-<task> with HTTPS origin https://github.com/ai-babai/brutforce.git.

## Board and repository permissions

Contributor requires repository Write and Project Writer, not GitHub admin. Read/create/update issues, branches, commits and PRs within assigned task scope. Direct messages from authorized participants can ask Sigma to create/manage cards elsewhere on this same project; preserve other people's assignments/work and record human initiator separately from account author.
Existing sigma-board helper mutates only Sigma-assigned cards; use gh for other explicitly requested project operations. Scheduled poll stays restricted to Sigma-assigned OPEN Backlog without blocked, one at a time. Do not broaden polling because API permissions allow it.

Before creating a card search for duplicates. Prefix FE/BE/ML/INFRA uses actual issue number. Fill Area, initiator, result criteria, executor and session. Link PR/commit/checks on completion. Follow /srv/lct/guide/docs/agent-guide/BOARD.md.
No auto merge to main or production deploy unless the task authorizes it. Force push, history rewriting, deleting data/access changes require separate explicit authorization. Github access does not expand Linux sudo rights.

## Account administration

Account email,2FA/passkeys,recovery remain controlled by the human owner; never install them on Sigma. Use a separate named expiring service token and record expiration/renewal metadata, not token value. Limit memberships of the service account: classic PAT scopes can apply to all repositories/projects it can access. Prefer a GitHub App if future separation/audit needs justify the extra setup.
