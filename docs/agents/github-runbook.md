# GitHub Issue Operations Runbook

## Purpose

This runbook contains the repeatable commands used to manage specifications,
implementation plans, labels, Work Packages, and native GitHub Sub-Issues for
this repository. The delivery sequence and decision gates remain in
`docs/agents/feature-workflow.md`.

Prefer narrow JSON output, `--jq`, and body files. This reduces shell quoting
errors, accidental context expansion, and repeated command discovery.

## Safety rules

- Infer the repository from the checked-out Git remote; do not hard-code a
  different owner or repository.
- Never call `gh auth token` or print authentication tokens.
- Never put passwords, API keys, device addresses, or other secrets in issue
  bodies, command arguments, logs, or committed files.
- Use Markdown body files under `/tmp` for generated issue content.
- Check for an existing issue before creating a new one.
- Creating issues, comments, labels, repository settings, or relationships is
  an external write and requires authorization.
- Do not enable repository features, close issues, publish releases, or change
  labels unless the requested workflow requires it.
- Treat a partially successful batch as recoverable. Inspect existing issues
  and relationships before retrying; do not create duplicates.

## Establish the GitHub context

### Verify authentication

```bash
gh auth status
```

If authentication is invalid, let the repository owner run or authorize:

```bash
gh auth login -h github.com -p ssh -w
```

Do not store credentials in the repository.

### Resolve the repository

Run commands from the repository working tree:

```bash
git remote -v
gh repo view --json nameWithOwner,url,hasIssuesEnabled
```

For reusable shell snippets:

```bash
repo_slug="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
```

Confirm that `repo_slug` identifies the intended fork before any write.

### Check CLI capabilities

```bash
gh --version
gh issue create --help | rg -- '--parent'
```

If `--parent` is listed, use the direct Sub-Issue workflow. If it is absent,
use the REST fallback below.

## Inspect issues without noisy output

### List issues

```bash
gh issue list \
  --state all \
  --limit 100 \
  --json number,title,state,labels,url \
  --jq '.[] | [.number, .state, .title, .url] | @tsv'
```

### Check for a possible duplicate

```bash
search_text="grid charging"
gh issue list \
  --state all \
  --search "$search_text in:title" \
  --json number,title,state,url
```

Search results can be approximate. Compare exact title, scope, and body before
reusing or creating an issue.

### Read one issue and its comments

```bash
issue_number=1
gh issue view "$issue_number" \
  --json number,title,body,state,labels,comments,url
```

Prefer explicit `--json` fields. Older CLI versions may make an unnecessary
GraphQL request for deprecated classic-project data when using the default
formatted view.

## Manage workflow labels

### List labels

```bash
gh label list \
  --limit 200 \
  --json name,description,color \
  --jq '.[] | [.name, .description, .color] | @tsv'
```

Canonical labels are defined in `docs/agents/triage-labels.md`.

### Create a missing label

Check first; do not overwrite an existing label merely to change its color or
description.

```bash
gh label create ready-for-agent \
  --description "Fully specified and agent-ready" \
  --color 0E8A16
```

### Move an issue between workflow states

```bash
issue_number=2
gh issue edit "$issue_number" \
  --remove-label needs-info \
  --add-label ready-for-agent
```

Remove stale state labels instead of accumulating contradictory states.

## Publish the specification as the parent issue

Prepare the complete specification in a temporary Markdown file:

```bash
spec_file=/tmp/feature-spec.md
```

Create the issue:

```bash
gh issue create \
  --title "Add concise feature title" \
  --body-file "$spec_file" \
  --label ready-for-agent
```

Capture the returned URL when later commands need the issue number:

```bash
parent_url="$(gh issue create \
  --title "Add concise feature title" \
  --body-file "$spec_file" \
  --label ready-for-agent)"
parent_number="${parent_url##*/}"
```

Use either creation example, not both.

### If Issues are disabled

Verify first:

```bash
gh repo view --json hasIssuesEnabled,url
```

Enabling Issues changes repository settings and requires explicit authority:

```bash
repo_slug="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
gh api --method PATCH "repos/$repo_slug" -F has_issues=true
```

## Publish the implementation plan

```bash
parent_number=1
plan_file=/tmp/implementation-plan.md

gh issue comment "$parent_number" --body-file "$plan_file"
```

Verify the last comment compactly:

```bash
gh issue view "$parent_number" \
  --json comments \
  --jq '.comments[-1] | {
    author: .author.login,
    url: .url,
    body_chars: (.body | length)
  }'
```

## Create Work Package issues

Each body should contain:

```markdown
Parent: #1
Work package: WP1
Blocked by: #2, #3

## Objective

## Scope

## Acceptance criteria

## Required tests

## Out of scope
```

Omit `Blocked by` when the Work Package has no dependencies. Use actual issue
numbers, not placeholders, before marking the issue `ready-for-agent`.

### Direct Sub-Issue creation with a capable CLI

```bash
parent_number=1
work_package_file=/tmp/wp1.md

gh issue create \
  --title "Add deterministic asynchronous test infrastructure" \
  --body-file "$work_package_file" \
  --label ready-for-agent \
  --parent "$parent_number"
```

### Fallback for a CLI without `--parent`

First create a normal issue:

```bash
work_package_file=/tmp/wp1.md
child_url="$(gh issue create \
  --title "Add deterministic asynchronous test infrastructure" \
  --body-file "$work_package_file" \
  --label ready-for-agent)"
child_number="${child_url##*/}"
```

Resolve the REST database ID. The issue number and database ID are different:

```bash
repo_slug="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
child_database_id="$(gh api \
  "repos/$repo_slug/issues/$child_number" \
  --jq .id)"
```

Attach the existing issue to the parent:

```bash
parent_number=1
github_api_version=2026-03-10

gh api \
  --silent \
  --method POST \
  "repos/$repo_slug/issues/$parent_number/sub_issues" \
  -H "X-GitHub-Api-Version: $github_api_version" \
  -F "sub_issue_id=$child_database_id"
```

This REST form was verified on 2026-07-19. Check the current official GitHub
Sub-Issues API documentation before changing the API-version value.

## Verify the Sub-Issue hierarchy

```bash
repo_slug="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
parent_number=1

gh api \
  "repos/$repo_slug/issues/$parent_number/sub_issues" \
  --paginate \
  --jq '.[] | [
    .number,
    .state,
    (.labels | map(.name) | join(",")),
    .title,
    .html_url
  ] | @tsv'
```

Confirm expected count, ordering, open/closed state, labels, and titles. Native
parent linkage does not replace explicit `Blocked by` execution dependencies.

## Edit an existing issue safely

Write the complete replacement body to a file and inspect it first:

```bash
issue_number=2
replacement_body=/tmp/issue-2.md

gh issue edit "$issue_number" --body-file "$replacement_body"
```

For a small append-only update, prefer a comment rather than rewriting the
specification or Work Package body.

```bash
gh issue comment "$issue_number" --body-file /tmp/validation-result.md
```

## Close completed work

Close a Work Package only after every acceptance criterion and required check
is complete:

```bash
child_number=2
gh issue close "$child_number" \
  --comment "Implemented and verified; checks are recorded in the linked PR."
```

Before closing the parent, verify all children:

```bash
gh api \
  "repos/$repo_slug/issues/$parent_number/sub_issues" \
  --paginate \
  --jq '.[] | [.number, .state, .title] | @tsv'
```

Do not close the parent while required software, release, or manual validation
gates remain unresolved.

## Batch-operation recovery

GitHub can apply secondary rate limits when many issues or relationships are
created quickly.

If a batch stops:

1. List existing issues and match exact Work Package titles.
2. List current Sub-Issues under the parent.
3. Reuse already-created issue numbers.
4. Retry only missing parent relationships.
5. Do not recreate successfully published issues.
6. Respect any `Retry-After` response instead of busy-looping.

The Sub-Issue link operation is independently retryable; a failed relationship
does not delete the child issue.

## Compact verification patterns

### Issue metadata

```bash
gh issue view "$issue_number" \
  --json number,title,state,labels,url \
  --jq '{
    number,
    title,
    state,
    labels: [.labels[].name],
    url
  }'
```

### Working tree after tracker-only work

```bash
git status --porcelain=v1
```

Tracker operations should not modify repository files. Temporary Markdown under
`/tmp` must not be staged or committed.

## When to automate further

Keep this runbook as the first level of reuse. Add a repository script only
after the same batch workflow has been repeated and its inputs are stable.

A future script should:

- accept parent number, title, body file, labels, and dependencies explicitly;
- detect direct `--parent` support and otherwise use the REST fallback;
- be idempotent or stop before creating a duplicate;
- emit only created/reused issue numbers and URLs;
- never read or print authentication tokens;
- fail without partially rewriting issue bodies;
- provide a dry-run mode before external writes.
