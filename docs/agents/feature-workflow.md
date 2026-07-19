# Feature and Bugfix Delivery Workflow

## Purpose

This guide defines the default workflow for turning an initial feature request
or bug report into implemented, verified, and traceable repository changes. It
applies to human maintainers and AI agents.

The workflow is deliberately evidence-first. Do not start implementation while
important product behaviour, safety constraints, failure semantics, or test
seams are still implicit.

## Source-of-truth hierarchy

Each artifact has one distinct responsibility. Do not duplicate the same text
across several files and issues.

Use `docs/agents/github-runbook.md` for the concrete GitHub CLI and REST
commands that implement the tracker portions of this workflow.

| Artifact | Location | Responsibility |
| --- | --- | --- |
| Repository instructions | `AGENTS.md` | Stable commands, constraints, conventions, and wayfinding |
| Domain context | `CONTEXT.md` | Canonical terms and meanings shared across features |
| Architecture decisions | `docs/adr/` | Durable decisions and their consequences |
| Product specification | Parent GitHub Issue | Required behaviour, acceptance, tests, and exclusions |
| Implementation plan | Comment in the parent issue | Technical modules, order, dependencies, and gates |
| Work packages | GitHub Sub-Issues | Independently executable and reviewable implementation work |
| User documentation | `README.md` and related docs | Supported user-facing operation and examples |
| Release history | `CHANGELOG.md` | User-visible delivered changes |

For a repository-sized feature or bugfix, prefer a specification. Use a PRD
only when a broader product initiative spans several specifications,
repositories, releases, or user journeys.

## Triage lifecycle

Use labels as workflow state, not decoration:

- `needs-triage`: the request exists but its validity, priority, or scope still
  needs maintainer evaluation.
- `needs-info`: progress is blocked on reporter or stakeholder information.
- `ready-for-agent`: decisions and acceptance criteria make the issue safely
  executable by an agent.
- `ready-for-human`: execution requires human-only access, judgment, hardware,
  credentials, or an external action.
- `wontfix`: the request has been deliberately declined with a recorded reason.

Remove stale state labels when the issue moves forward. A child issue can be
`ready-for-agent` while the parent retains an unresolved manual production gate.

## Workflow overview

```text
Request or bug report
        |
        v
Baseline, evidence, and risk assessment
        |
        v
Grilling session and explicit decisions
        |
        v
CONTEXT.md -> AGENTS.md -> ADRs
        |
        v
Specification -> Parent GitHub Issue
        |
        v
Implementation plan
        |
        v
GitHub Sub-Issues / Work Packages
        |
        v
Implement -> Test -> Review each Work Package
        |
        v
Integration, manual gates, documentation, release
        |
        v
Close Sub-Issues and parent issue
```

Stages may reveal missing information. Move back to the responsible artifact
instead of hiding a new decision inside implementation code.

## Stage 0: Establish the Ausgangslage

### Goal

Create a verified baseline before discussing a solution.

### Actions

1. Classify the request as feature, bugfix, maintenance, or investigation.
2. Read `AGENTS.md`, `CONTEXT.md`, relevant ADRs, existing issues, and recent
   changes before proposing a design.
3. Locate the current runtime path and its interfaces. Record what the system
   does today, not what it is assumed to do.
4. For a bug, obtain the smallest reliable reproduction, exact error, expected
   behaviour, actual behaviour, affected versions, and regression range when
   known.
5. For a feature, identify the user, their goal, the system seam, inputs,
   outputs, and why existing behaviour is insufficient.
6. Capture relevant environment details: Python and dependency versions,
   operating system, hardware model, firmware, broker or service versions, and
   configuration mode.
7. Search existing upstream issues, documentation, protocol evidence, and
   comparable implementations. Prefer primary sources and link them.
8. State unavailable evidence explicitly, especially missing hardware tests,
   packet captures, credentials, or production access.
9. Classify risk: physical writes, data loss, security, credentials,
   compatibility, migrations, concurrency, retries, and external side effects.
10. Confirm repository health with proportionate existing checks. Do not blame
    pre-existing failures on the new work.

### Exit criteria

- The current and desired behaviour are distinguishable.
- Evidence and assumptions are labelled separately.
- Known constraints and unavailable validation are visible.
- The request is specific enough to grill without prematurely designing code.

## Stage 1: Run the grilling session

### Goal

Turn implicit expectations into explicit, confirmed decisions before writing a
specification.

### Method

- Ask one focused question at a time.
- Challenge ambiguous terms, optimistic assumptions, hidden state, and unsafe
  defaults.
- Explain material trade-offs in plain language before asking for a decision.
- Record each accepted answer. Do not repeatedly reopen settled decisions
  unless new evidence conflicts with them.
- Separate product behaviour from implementation choices.
- Mark unresolved questions and identify whether they block the specification,
  implementation, release, or only production validation.

### Required topics

Cover the relevant items, not merely the happy path:

- Supported users, devices, models, versions, and environments.
- Exact input format, validation, ranges, units, steps, and normalization.
- Output, state, acknowledgement, error, and observability semantics.
- Ownership and writer model, including concurrent or duplicate requests.
- Retain, replay, retry, timeout, ordering, rate-limit, and idempotency rules.
- Startup, shutdown, reconnect, persistence, and failure behaviour.
- Configuration source, defaults, precedence, secrets, schema evolution, and
  reload policy.
- Backward compatibility and migration expectations.
- Security, privacy, physical safety, and destructive-action constraints.
- Scope exclusions and deliberately unsupported behaviour.
- Test seam, fake adapters, deterministic time, and required manual tests.
- Release gate, experimental status, rollback, and recovery behaviour.

### Bugfix additions

- Confirm the reproduction before debating the fix.
- Identify the earliest seam at which the wrong behaviour becomes observable.
- Define a regression test that fails for the original defect.
- Distinguish root cause from symptoms and estimate the blast radius.

### Exit criteria

- All behaviour-changing choices are confirmed or explicitly deferred.
- Error and failure semantics are as clear as success semantics.
- A deterministic automated test seam exists.
- Hardware- or production-only validation has a separate manual gate.

## Stage 2: Create or update `CONTEXT.md`

### Goal

Establish a shared domain language before specifications and code introduce
competing terminology.

### Rules

- Read the existing context first and preserve valid established terms.
- Add only durable domain concepts shared by multiple modules or actors.
- Define what each term means and, where useful, what misleading alternatives
  should be avoided.
- Describe business or protocol meaning, not a Python class or file layout.
- Keep feature-specific acceptance criteria in the specification.
- Skip this update when the request introduces no new domain language.

### Exit criteria

- The specification can use one canonical term for every important concept.
- State, command, acknowledgement, measurement, and configured intent are not
  conflated.

## Stage 3: Update `AGENTS.md` when necessary

### Goal

Keep stable repository guidance accurate for future work.

### Update when

- The repository map, supported runtime, setup, validation commands, or test
  commands changed.
- A new durable safety constraint or development convention applies beyond one
  issue.
- New documentation provides required wayfinding for agents.

### Do not add

- The complete feature specification.
- Temporary implementation notes or ticket status.
- Credentials, device addresses, packet logs, or local environment details.

The initial planning pass may add wayfinding. Review `AGENTS.md` again after
implementation so its commands and repository map reflect delivered reality.

## Stage 4: Record architecture decisions

### Goal

Preserve durable choices that constrain several modules or future features.

### When an ADR is warranted

- Several reasonable alternatives exist.
- The decision changes an interface, seam, persistence model, configuration
  strategy, protocol contract, or safety policy.
- Future maintainers could otherwise reverse the choice without understanding
  its consequences.

### ADR guidance

- Store one decision per file under `docs/adr/`.
- Use sequential numbering and a concise decision title.
- Record status, context, decision, important alternatives, and consequences
  when those details are material.
- Link superseding ADRs instead of silently rewriting accepted history.
- Do not create an ADR for a local mechanical implementation detail.

### Exit criteria

- The specification can reference architectural choices rather than silently
  embedding them.
- No accepted ADR conflicts with the planned behaviour.

## Definition of Ready for the specification

Before creating the specification, confirm:

- [ ] Problem and desired outcome are evidence-backed.
- [ ] Supported and unsupported scope is explicit.
- [ ] Canonical domain language exists.
- [ ] Material architecture choices are recorded.
- [ ] Inputs, outputs, state, errors, timing, and failure behaviour are decided.
- [ ] Security, compatibility, and physical-safety risks are addressed.
- [ ] Automated and manual validation seams are known.
- [ ] Remaining unknowns have an owner and a blocking level.

## Stage 5: Write the specification

### Goal

Describe what must be true when the work is complete without turning the spec
into a file-by-file coding script.

### Recommended structure

1. **Problem Statement** — current limitation and user impact.
2. **Solution** — intended behaviour and system responsibility.
3. **User Stories** — numbered, testable outcomes including failure paths.
4. **Implementation Decisions** — confirmed contracts and constraints.
5. **Testing Decisions** — automated seam, fakes, fixtures, and manual gates.
6. **Out of Scope** — explicit exclusions.
7. **Further Notes** — evidence, versions, experimental status, and references.

### Quality rules

- Use canonical terms from `CONTEXT.md`.
- State exact topics, payload shapes, units, ranges, defaults, timing, and stable
  errors when they form part of the interface.
- Distinguish configured intent, acknowledged state, and measured state.
- Include backward-compatibility and migration requirements.
- Avoid unresolved adjectives such as safe, fast, current, or robust without a
  measurable meaning.
- Do not claim hardware validation that has not occurred.

## Stage 6: Publish the parent GitHub Issue

### Goal

Make one parent issue the product-level source of truth and tracking root.

### Actions

1. If a suitable issue already exists, update it instead of creating a
   duplicate.
2. Put the complete specification in the issue body.
3. Link upstream reports, source evidence, ADRs, and relevant context.
4. Apply `needs-info` while blocking decisions are unresolved.
5. Apply `ready-for-agent` only after the Definition of Ready is satisfied.
6. Keep implementation progress out of the specification body unless it
   changes the required behaviour.

For bug reports that already started as issues, preserve the original report
and add or link the refined specification clearly.

## Stage 7: Create the implementation plan

### Goal

Translate required behaviour into a safe technical delivery order based on the
actual current codebase.

### Actions

1. Reinspect the affected runtime path; do not plan against remembered code.
2. Identify modules, their interfaces, and the real seams needed for production
   and fake adapters.
3. Prefer deep modules: small interfaces that hide validation, state, timing,
   protocol, or configuration complexity.
4. Define independently reviewable Work Packages.
5. State dependencies and opportunities for safe parallel work.
6. Prevent incomplete or unsafe functionality from being publicly exposed.
7. Add validation gates: safety, protocol, exposure, software-complete, manual
   hardware or production, and release.
8. Define the parent issue's Definition of Done.
9. Publish the implementation plan as a comment on the parent issue.

The plan may name likely files and interfaces. It must remain about delivery
shape rather than reproducing the specification.

## Stage 8: Create GitHub Sub-Issues as Work Packages

### Goal

Turn the plan into executable tickets with clear ownership and dependencies.

### Required Work Package structure

- `Parent: #<issue>` and a stable Work Package identifier.
- **Objective** — one concrete outcome.
- **Scope** — included implementation responsibilities.
- **Acceptance criteria** — observable checkboxes.
- **Required tests** — behaviour proven at the module interface.
- **Dependencies** — actual `Blocked by: #...` issue references.
- **Out of scope** — protections against expansion.

### Rules

- Use native GitHub Sub-Issues under the parent when available.
- Apply `ready-for-agent` only when the ticket is independently executable.
- Size each Work Package for one coherent review. Split it when unrelated
  interfaces, risks, or validation gates would otherwise be mixed.
- Dependencies must form an acyclic graph.
- Keep cross-cutting final integration and documentation work explicit.
- Do not create tickets that merely say "implement the spec".

## Stage 9: Execute the Work Packages

### Preparation

1. Ensure planning and documentation commits are preserved and pushed when
   collaboration requires them.
2. Create a focused branch from the intended base.
3. Read the parent issue, implementation plan, current Work Package, context,
   ADRs, and repository instructions.
4. Confirm that all blocker issues are complete.

### Implementation loop

For each Work Package:

1. Reproduce the target behaviour or establish the failing acceptance test.
2. Implement the smallest coherent behaviour through the planned interface.
3. Prefer red-green-refactor for bugfixes and safety-critical behaviour.
4. Test observable results through interfaces; do not couple tests to private
   implementation structure.
5. Run focused tests during development and proportionate repository checks
   before completion.
6. Inspect the diff for unrelated changes, secrets, generated files, unsafe
   writes, compatibility breaks, and missing documentation.
7. Perform code review against both repository standards and the originating
   specification.
8. Commit one logical change with a Conventional Commit message and reference
   the Work Package issue.
9. Push the branch and open or update an implementation pull request when the
   repository uses pull requests. Link the Work Package and parent issue, but do
   not close the parent prematurely.
10. Require green checks and resolved review findings before merge. Preserve a
    reviewable commit history according to repository policy.
11. Update the issue with checks run, limitations, and hardware validation not
   performed.
12. Merge and close the Work Package only when every acceptance criterion is
    met.

### Failure handling

- If implementation exposes a missing product decision, pause and update the
  parent specification before continuing.
- If it exposes a durable architecture conflict, create or supersede an ADR.
- If scope grows materially, create another Work Package instead of silently
  expanding the active one.
- Never weaken tests, validation, or safety constraints merely to make a ticket
  pass.

## Stage 10: Integration, release, and operational validation

### Automated gate

- Run the full test suite, style checks, dependency checks, and distribution
  build required by `AGENTS.md` and CI.
- Exercise the complete cross-module flow with deterministic fake adapters.
- Confirm backward-compatible CLI, configuration, MQTT, and Home Assistant
  behaviour unless a breaking change was explicitly approved.

### Documentation gate

- Update `README.md`, examples, configuration reference, and troubleshooting.
- Add user-visible changes under `FUTURE` in `CHANGELOG.md`.
- Document migrations, deprecations, safe operating order, observability, and
  recovery behaviour where relevant.
- Review `AGENTS.md`, `CONTEXT.md`, and ADRs against the delivered code.

### Manual or hardware gate

- Require explicit authorization and a known-safe environment for physical or
  destructive tests.
- Record device, firmware, configuration, procedure, expected result, actual
  result, and rollback steps.
- Keep the feature experimental when the manual gate cannot yet be completed.
- Never equate a protocol acknowledgement with measured physical behaviour.

### Release and rollback gate

- Define how the change is enabled, observed, disabled, and rolled back.
- Confirm secrets are not committed or logged.
- Do not publish packages or create tags unless explicitly authorized.

## Stage 11: Close the work

1. Verify every Sub-Issue is complete and its acceptance evidence is recorded.
2. Run the parent Definition of Done against the integrated result.
3. Close the parent issue only after required software and release gates pass.
4. Leave blocked manual validation open or explicitly tracked; do not imply it
   happened.
5. Record follow-up work as new issues rather than burying it in a closing
   comment.
6. Update or supersede planning artifacts when implementation legitimately
   changed a prior decision.
7. Capture lessons only when they produce durable repository guidance, domain
   language, or architecture decisions.

## Definition of Done

- [ ] Parent specification and implemented behaviour agree.
- [ ] All required Work Packages are complete.
- [ ] Automated acceptance and regression tests pass.
- [ ] Full repository validation passes.
- [ ] Security, compatibility, migration, and safety checks are complete.
- [ ] User documentation and changelog are updated.
- [ ] Agent instructions, context, and ADRs match delivered reality.
- [ ] Manual or hardware validation is complete or transparently remains a
      tracked release blocker.
- [ ] Rollback or disablement is understood for risky changes.
- [ ] No credentials, local addresses, logs, virtual environments, or generated
      artifacts were committed.
- [ ] GitHub hierarchy, labels, dependencies, and closing status are accurate.

## Common failure modes

- Coding before success, failure, and safety semantics are agreed.
- Treating an upstream implementation as proof for different hardware.
- Mixing domain terms, architecture decisions, specifications, and ticket
  status in one document.
- Publishing a setter before validation, acknowledgement, timeout, and retry
  behaviour exist.
- Creating broad Work Packages with no independent acceptance criteria.
- Testing internal call sequences instead of observable module behaviour.
- Using real sleeps, brokers, or hardware where deterministic adapters suffice.
- Closing the parent issue while manual release gates remain ambiguous.
- Duplicating the specification in a repository Markdown file and allowing it
  to drift from the GitHub issue.
