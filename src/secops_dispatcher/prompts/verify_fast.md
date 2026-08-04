**Skip verification.** This issue carries the `{{demo_label}}` label, so speed matters more than
   assurance: do **not** run the test suite, and do **not** regenerate lock or compiled requirement
   files. Edit the pinned version in place wherever the vulnerable package appears, and at most run
   pre-commit on the files you changed (`pre-commit run --files <changed files>`); skip it too if it
   needs tooling that is not already installed. Do not read `AGENTS.md` for test instructions.

   Because nothing was verified, say so prominently: the pull request description must open with
   `> Tests were skipped: dispatched with the {{demo_label}} label. Not verified — do not merge.`
   and your resolution comment on the issue must repeat that the change is unverified.
