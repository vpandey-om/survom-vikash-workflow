#!/usr/bin/env bash
set -euo pipefail

# Usage:
# bash scripts/finish_branch_and_start_new.sh \
#   "feat(common): add inspect inputs" \
#   "v0.1.0-common-inspect-inputs" \
#   "step/common-differential-plan"

COMMIT_MESSAGE="${1:?Commit message is required}"
TAG_NAME="${2:?Tag name is required}"
NEW_BRANCH="${3:?New branch name is required}"

CURRENT_BRANCH="$(git branch --show-current)"

if [[ -z "${CURRENT_BRANCH}" || "${CURRENT_BRANCH}" == "master" ]]; then
  echo "ERROR: Run this from a feature/step branch, not master."
  exit 1
fi

echo "Current branch: ${CURRENT_BRANCH}"
echo "Commit message: ${COMMIT_MESSAGE}"
echo "Tag: ${TAG_NAME}"
echo "New branch: ${NEW_BRANCH}"
echo

git status --short

read -r -p "Commit, merge into master, tag, delete '${CURRENT_BRANCH}', and create '${NEW_BRANCH}'? [y/N] " CONFIRM

if [[ "${CONFIRM}" != "y" && "${CONFIRM}" != "Y" ]]; then
  echo "Cancelled."
  exit 0
fi

# Commit current work.
git add -A
git commit -m "${COMMIT_MESSAGE}"

# Update master and merge current branch.
git switch master
git pull --ff-only
git merge --no-ff "${CURRENT_BRANCH}" -m "merge: ${CURRENT_BRANCH}"

# Create annotated tag on the merge commit.
git tag -a "${TAG_NAME}" -m "${TAG_NAME}"

# Delete merged local branch.
git branch -d "${CURRENT_BRANCH}"

# Start the next atomic-step branch from updated master.
git switch -c "${NEW_BRANCH}"

echo
echo "Done."
echo "Now on branch: $(git branch --show-current)"
echo "Latest commit:"
git log --oneline -1
echo "Tag created:"
git tag --list "${TAG_NAME}"