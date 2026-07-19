# Issue tracker: GitHub

Issues and specifications for this repository live as GitHub Issues. Use the
`gh` CLI for all operations and infer the repository from `git remote -v`.

## Conventions

- Create an issue with `gh issue create`.
- Read an issue and its discussion with `gh issue view <number> --comments`.
- List issues with `gh issue list`, including labels and comments when needed.
- Comment with `gh issue comment <number>`.
- Apply or remove labels with `gh issue edit <number>`.
- Close issues with `gh issue close <number>`.

## Pull requests as a triage surface

PRs as a request surface: no.

## Skill operations

When a skill says to publish to the issue tracker, create a GitHub Issue. When
a skill says to fetch a ticket, read the corresponding GitHub Issue including
its comments and labels.

For wayfinding, prefer GitHub sub-issues and native issue dependencies. If the
repository does not support them, use task lists for child issues and a
`Blocked by: #<number>` line for dependency edges.
