# Git Basics — Day-to-Day Cheat Sheet

A short reference for the everyday git loop on this repo. For the
ROGUE-specific branching model and Claude Code workflow, see
`ROGUE_Git_Claude_Development_Guide.md` in this same folder — this
document is just "how do I actually type the commands."

## The basic loop

Almost everything you do, day to day, is this cycle:

```bash
git status              # what changed?
git add <files>          # stage what you want to commit
git commit -m "message"  # save a checkpoint
git push                 # send it to GitHub
```

Do this often — after each small piece of work that runs/passes,
not once at the end of the day. Small commits are easier to undo,
easier to review, and much easier to reason about later.

## Checking what you're looking at

| Command | What it tells you |
|---|---|
| `git status` | Which branch you're on, what's staged, what's modified, what's untracked |
| `git diff` | Unstaged changes — what `git add` hasn't picked up yet |
| `git diff --cached` | Staged changes — what a commit right now would actually contain |
| `git log --oneline -10` | Last 10 commits, one line each |
| `git branch` | Local branches, `*` marks the current one |
| `git branch -vv` | Same, plus which remote branch each one tracks and ahead/behind counts |

Run `git status` before doing almost anything else — before adding,
before switching branches, before pulling. It's free and it tells you
exactly where you stand.

## Making a commit

```bash
git status                        # see what changed
git add path/to/file.py           # stage specific files (prefer this over `git add .`)
git diff --cached                 # double-check what you're about to commit
git commit -m "short, clear description of what changed"
```

Prefer adding specific files or folders by name rather than `git add .`
or `git add -A` — those can accidentally sweep in files you didn't mean
to commit (stray config, large data files, a `.env`). If you only ever
add what you intend to add, `git status` before committing is your
safety net.

## Working with branches

Never commit directly to `main`, and on this repo prefer not to commit
directly to `develop` either — do real work on a feature branch, then
open a Pull Request into `develop`:

```bash
git checkout develop
git pull                          # make sure develop is current before branching
git checkout -b feature/short-description

# ... make changes, add, commit as above ...

git push -u origin feature/short-description   # first push of a new branch needs -u
git push                                       # every push after that, just this
```

`-u` (or `--set-upstream`) tells git which remote branch this local
branch corresponds to — you only need it once per branch, the first
time you push it. After that, plain `git push` knows where to send it.

To open the Pull Request:

```bash
gh pr create --base develop --title "..." --fill
```

or do it on github.com if you don't have `gh` set up.

Once it's merged on GitHub, clean up locally:

```bash
git checkout develop
git pull
git branch -d feature/short-description
```

## Checks to run periodically (not just when something breaks)

**Before you start working each session:**

```bash
git status                # confirm you don't have leftover uncommitted changes
git checkout develop
git pull                  # make sure you have the latest merged work
```

**Before switching branches:**

```bash
git status
```

If this shows uncommitted changes, either commit them or
`git stash` before switching — git will refuse to switch if it would
overwrite modified files, but it's better to know why up front.

**Before pushing:**

```bash
git diff --cached         # or git show HEAD, to see what the last commit actually contains
git log --oneline -5      # sanity-check recent history
```

**Before opening a PR / periodically on an active feature branch:**

```bash
git fetch origin
git log --oneline develop..HEAD     # commits on your branch not yet in develop
git log --oneline HEAD..origin/develop   # commits in develop you don't have yet
```

If the second one shows anything, `develop` has moved on since you
branched — rebase or merge before your PR, rather than finding out
from a conflict on GitHub.

**Weekly-ish, or before anything you'd call a milestone:**

```bash
git branch -vv             # any local branches you forgot to delete after merging?
git branch -r               # what actually exists on the remote?
```

## Things that bit us already — worth remembering

- `git branch -M <name>` **renames the branch you're currently on** —
  it does not create a new branch and switch to it. Double-check
  `git status` for your current branch name before using `-M`.
- GitHub no longer accepts your account password for `git push` over
  HTTPS — use a Personal Access Token as the password, or (simpler
  long-term, and what this repo now uses) SSH with a registered key.
- `git diff` (no `--cached`) shows nothing right after `git add` — that's
  expected, not a sign nothing happened. The staged content shows in
  `git diff --cached` instead.
- Don't `git add` inside `examples/sigmf/` or anywhere IQ recordings
  might land — `.gitignore` already blocks `*.sigmf-data`/`*.iq`/`*.raw`,
  but double-check `git status` doesn't show a large file about to be
  staged before you commit.
