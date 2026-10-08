# greek-utils

<!-- onboard:agent-conventions -->
## Agent conventions

Written by `onboard repo` (thyra `scripts/onboard.py`, template `config/onboard/agent-conventions.md`). Change the template there and re-run `onboard repo greek-utils`, rather than editing between the markers. Anything outside the markers is this repo's own and wins on specifics.

- Commit and push finished, verified work directly to `main`, without waiting to be asked. No feature branch or pull request unless the task asks for one. Run the repo's own gate first.
- Stage only the files you touched, by name, never `git add -A` or `git add .`. Uncommitted files you did not write belong to another session: leave them alone, and if they block a rebase, `git stash push -u -- <paths>` and pop them afterward.
- Never force-push, `git reset --hard`, or otherwise discard work without asking.
- Track follow-up work as a GitHub issue in this repo, triaged when you open it: exactly one `type:*` label and exactly one of `agent-ok` or `needs-human`.
- A new recurring job is not finished until it is registered: `onboard pipeline <id>` writes the Operations registry entry and the launchd plist, then runs the registry procedure.
<!-- /onboard:agent-conventions -->
