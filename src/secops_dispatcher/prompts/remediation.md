You are remediating a security vulnerability tracked in a GitHub issue. Follow every step below in
order, and do not skip a step even if it looks unnecessary.

## Context

- Issue: {{issue_url}}
- Issue title: {{issue_title}}
- Repository to fix: `{{repo}}`
- Tracking project: "{{project_name}}" ({{project_url}})

Issue body:

```
{{issue_body}}
```

## Process

1. Comment `Starting remediation` on issue #{{issue_number}} in `{{repo}}`, then move the issue to
   **In Progress** in the "{{project_name}}" GitHub Project.
2. Create a new branch from `main` in `{{repo}}` for the remediation work.
3. Upgrade the vulnerable package(s) identified in the issue to the lowest version that fixes the
   vulnerability. Change only what is needed to fix it — do not upgrade unrelated dependencies. If
   the fixed version is unclear from the issue, determine it from the linked advisory (CVE/GHSA).
4. Read `AGENTS.md` in `{{repo}}` and follow its instructions for pre-commit checks and for running
   the tests, to verify the software still functions with the upgraded packages. If tests fail
   because of the upgrade, fix the incompatibility as part of this work.
5. Open a pull request with your changes, then move the issue to **In Review** in the
   "{{project_name}}" GitHub Project.
6. Comment on issue #{{issue_number}} with the resolution — the package(s) upgraded, the versions
   before and after, and how you verified the change — and link the issue to the pull request you
   opened.

## Notes

- If you cannot determine a fixed version, or the upgrade cannot be made to pass the checks in
  `AGENTS.md`, stop and explain the blocker in a comment on the issue instead of opening a PR that
  does not build.
- Do not close the issue; a human reviews the pull request.
