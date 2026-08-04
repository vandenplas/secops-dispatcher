This session has a secret named `GITHUB_PROJECT_TOKEN`: a GitHub PAT with write access to the
project. **Use it for the two board moves.** Your default GitHub credentials cannot write to the
project — an `updateProjectV2ItemFieldValue` mutation with them fails with
`FORBIDDEN: Resource not accessible by integration` — so a board move that appears to have worked
without this token was really the project's own automation, not you.

Read the ids once, then move the item with a mutation, e.g.

```bash
export GH_TOKEN="$GITHUB_PROJECT_TOKEN"

# Project id, the Status field id, and its option ids:
gh api graphql -f query='
  query { {{project_owner_kind}}(login: "{{project_owner}}") { projectV2(number: {{project_number}}) {
    id
    field(name: "Status") { ... on ProjectV2SingleSelectField { id options { id name } } }
  } } }'

# The item id for issue #{{issue_number}} (page through items if needed):
gh api graphql -f query='
  query { {{project_owner_kind}}(login: "{{project_owner}}") { projectV2(number: {{project_number}}) {
    items(last: 50) { nodes { id content { ... on Issue { number } } } }
  } } }'

gh api graphql -f query='
  mutation { updateProjectV2ItemFieldValue(input: {
    projectId: "<project id>", itemId: "<item id>",
    fieldId: "<Status field id>", value: { singleSelectOptionId: "<option id>" }
  }) { projectV2Item { id } } }'
```

After each move, read the item's `Status` back and confirm the new value. Treat any `FORBIDDEN`
response as the step having failed, and say so on the issue — do not assume a move worked because the
board happens to show the right column. (`Status.creator` is the login that first set the field, not
the last actor, so it is not evidence either way.) If the issue is not on the board yet, add it with
`addProjectV2ItemById`.
