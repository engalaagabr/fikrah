# Project Working Rules

When in doubt, stop and ask the user.

## Branches and Merging

- Work only on `dev`. Working directly on `main` is forbidden.
- Start each feature on its own branch created from `dev`, named `feature/<short-descriptive-name>`.
- A feature is complete only when all of the following are true:
  - The code works as specified.
  - Relevant tests are written and passing.
  - The related documentation is updated.
- When a feature is complete, push its feature branch to `origin` and open a pull request targeting `dev`.
- Merge completed pull requests into `dev` using a merge commit (the equivalent of `--no-ff`). Do not squash or rebase the pull request.
- Never push directly to `dev` or `main`.
- If a merge conflict occurs, stop and ask the user. Do not resolve it on your own.
- If the Git repository or the `dev` branch does not exist, ask the user before initializing the repository or creating the branch.

## Commits

- Break work into small, logical micro-commits. Each commit should do one thing and leave the project in a working state.
- Use Conventional Commits for messages (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`).
- Make the commits yourself on the feature branch; do not wait for approval between commits.
- Push only completed feature branches to `origin` for their pull requests. Never force-push.
- Before pushing to a public repository, verify that the commit author and committer identities will not attribute the work to the agent. Do not falsify authorship or impersonate the user to affect the contributor list. If the attribution cannot be verified or would identify the agent, stop and explain the issue before pushing.

## Forbidden Git Operations

Never run the following without explicit permission from the user:

- `git push` (in any form, including `--force`)
- Pushing directly to `dev` or `main`.
- `git reset --hard`
- `git rebase` on any branch that has been shared or merged
- Deleting branches
- Rewriting history (`git commit --amend` on commits that were already merged, `git filter-branch`, etc.)

## Testing

- Write tests for each feature alongside the code.
- Run the tests before every merge into `dev`. Do not merge if tests fail.

## Planning and Documentation

- Divide the project into phases and document each phase in a descriptively named file under `docs/phases/<phase>/`.
- Divide the work into features and document each feature in a descriptively named file under `docs/features/<feature>/`.
- Name files by their contents (for example `overview.md`, `api-design.md`, `decisions.md`). Never name every file the same thing.
- Write project documentation in English by default. Use Arabic when the user requests it.
- Update the relevant phase or feature documentation when a change affects behavior, scope, or design. Minor internal changes (renames, formatting, small refactors) do not require a docs update.

## Communication and Decisions

- Ask the user before deciding anything about project requirements or behavior.
- For small technical details that do not affect requirements or behavior (variable names, internal structure, formatting), decide yourself and mention the choice in the commit message or the feature doc.
- If information is missing or something is unclear in a way that affects requirements, ask the user before implementing.
- If two rules seem to conflict, stop and ask the user.
