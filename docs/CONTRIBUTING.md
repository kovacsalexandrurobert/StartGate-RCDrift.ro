# Contributing (trunk-based)

`main` is the only long-lived branch. **Do not push commits straight to `main`.** GitHub rules require a pull request.

## Workflow

1. Update `main` locally: `git checkout main && git pull`.
2. Create a short-lived branch for one change:

   ```text
   git checkout -b feature/<short-name>
   ```

   Also fine: `fix/…`, `docs/…`, `chore/…`. One concern per branch.

3. Commit on that branch. Push: `git push -u origin HEAD`.
4. Open a PR into `main`. Prefer **squash** (or rebase). Merge commits are disabled.
5. After merge, the feature branch is deleted on GitHub. Delete the local branch too.

## Rules enforced on `main`

- Pull request required (no direct pushes, including for admins)
- Force-push blocked
- Branch deletion of `main` blocked
- Squash or rebase merge only
- Feature branch deleted automatically after merge

Approvals are not required (solo-friendly). Add reviewers when you want a second pair of eyes.
