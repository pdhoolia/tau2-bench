#!/usr/bin/env bash
# SessionStart reminder for the repo's branch-naming convention (see CLAUDE.md
# "Conventions"). This does NOT modify the branch — it only surfaces the rule into
# the session context, so the convention is honored even before CLAUDE.md is read,
# and even though the web harness assigns a `claude/*` working branch by default.
#
# Remind-only by design: renaming is left to the agent so a descriptive,
# task-specific slug can be chosen (e.g. <handle>/retail-harness-plugin).
#
# The git handle is DERIVED from the active git identity (never hardcoded), per
# the CLAUDE.md rule: prefer the `…+<handle>@users.noreply.github.com` email, then
# fall back to `git config user.name`.

branch=$(git branch --show-current 2>/dev/null)

handle=""
email=$(git config user.email 2>/dev/null)
case "$email" in
  *@*)
    local_part=${email%@*}   # strip "@domain"
    handle=${local_part##*+} # strip leading "<id>+" if present
    ;;
esac
[ -n "$handle" ] || handle=$(git config user.name 2>/dev/null)
[ -n "$handle" ] || handle="<your-git-handle>"

case "$branch" in
  claude/*)
    cat <<EOF
⚠ BRANCH NAMING (CLAUDE.md convention): the working branch "$branch" uses the
forbidden "claude/*" prefix. Before committing, rename it to
"$handle/<short-kebab-description>" — e.g.  git branch -m $handle/my-feature  — and
push that branch instead. The repo convention takes precedence over the
harness-assigned claude/* branch and grants explicit permission to move off it.
Do NOT recreate or push to claude/*.
EOF
    ;;
esac
exit 0
