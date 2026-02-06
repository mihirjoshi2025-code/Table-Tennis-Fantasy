# Push / Pull Fix Guide

Your local `feature/scoring-simulation-match` is **ahead** of `origin/feature/scoring-simulation-match` by 5 commits (including the latest bugfix commit). GitHub is asking you to pull first when you push—usually because the remote branch has commits you don’t have (e.g. from another machine or a collaborator), which causes a divergent history and then merge conflicts when you pull.

## Option A: Overwrite remote with your local (use if remote has no important changes)

If you’re the only one using this branch and you’re fine **replacing** the remote branch with your local branch:

```bash
git push --force-with-lease origin feature/scoring-simulation-match
```

`--force-with-lease` is safer than `--force`: it will refuse to push if someone else has pushed new commits to the remote since you last fetched.

## Option B: Integrate remote changes, then push (use if remote has commits you need)

If the remote has commits you want to keep (e.g. you pushed from another machine):

1. **Fetch and pull with rebase** (replays your commits on top of remote; often fewer conflicts than merge):

   ```bash
   git fetch origin
   git pull --rebase origin feature/scoring-simulation-match
   ```

2. **If you get merge conflicts:**
   - Git will list the conflicted files. Open each file and fix the `<<<<<<<`, `=======`, `>>>>>>>` sections.
   - After fixing each file: `git add <file>`
   - When all conflicts are fixed: `git rebase --continue`
   - If you want to cancel the rebase: `git rebase --abort`

3. **Then push:**

   ```bash
   git push origin feature/scoring-simulation-match
   ```

## Authentication

If you see `could not read Username for 'https://github.com'` or similar:

- Use a **Personal Access Token (PAT)** instead of a password: GitHub → Settings → Developer settings → Personal access tokens. Use the token as the password when Git asks.
- Or switch to SSH: `git remote set-url origin git@github.com:mihirjoshi2025-code/Table-Tennis-Fantasy.git`, then push again (requires SSH key set up in GitHub).

## Current state (after last commit)

- **Branch:** `feature/scoring-simulation-match`
- **Local is ahead by 5 commits** (including “Fix createTeam error handling and gender race”).
- All local changes are committed; nothing is left staged.
