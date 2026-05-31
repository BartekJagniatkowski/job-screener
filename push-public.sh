#!/usr/bin/env bash
set -euo pipefail

# Push to public remote with CHANGELOG.public.md substituted in as CHANGELOG.md.
# Creates a synthetic commit on top of HEAD — does not modify the working tree,
# does not create any local branches, requires no force-push.

REMOTE="${1:-public}"
BRANCH="${2:-main}"

echo "Building public tree..."

# Write CHANGELOG.public.md as a blob and get its hash
BLOB=$(git hash-object -w CHANGELOG.public.md)

# Rebuild the tree with CHANGELOG.md replaced by that blob
TREE=$(git ls-tree HEAD | sed "s/[^ ]* blob [^ ]*\tCHANGELOG.md/100644 blob $BLOB\tCHANGELOG.md/" | git mktree)

# Create a synthetic commit on top of HEAD with the substituted tree
COMMIT=$(git commit-tree "$TREE" -p HEAD -m "chore: sync public changelog")

echo "Pushing $COMMIT to $REMOTE/$BRANCH..."
git push "$REMOTE" "$COMMIT:refs/heads/$BRANCH"

echo "Done. Public repo has CHANGELOG.public.md as CHANGELOG.md."
echo "Dev repo is unchanged."
