# Evaluating further

The public site at <https://evalbench-demo.onrender.com> is a read-only mock
demo. It shows one caught regression. It does not clone a repository a visitor
pastes in, and it does not call a paid model. A repository is evaluated by
adding the regression-gate workflow and opening a pull request.

These are the three major evaluations still ahead. The first one records the
branch pair now. The other two are not implemented.

## 1. Branch comparison on the pull request

Compare the head branch with the baseline committed from the base branch, on
the same dataset and split. The gate already does that score comparison. On a
pull request it now also records `base_ref`, `head_ref`, and `head_sha` in
`reports/gate.json` and in the GitHub step summary, next to the mean score
delta and the newly failing examples.

This is the comparison a recruiter can trust: the dataset is pinned, the
prompts are hashed, and a known-bad prompt exits 1.

## 2. A dataset the repository commits

Let a project commit its own JSONL dataset, prompt, and deterministic scorer
settings, then run the same gate. The upload is a commit in that repository,
reviewed in the pull request, content-hashed, and scored without executing
repository code as the evaluator. Exact match, token F1, answerability, and
JSON Schema stay the scores. A form on the public demo that accepts a Git
URL would run untrusted code and is out of scope.

## 3. A judge that has earned the gate

Keep model judges out of the release decision until a holdout study passes the
passport: agreement with human labels, repeatability, stable order swaps, and
a verbosity check. The October 13, 2026 session stored 3 assisted holdout
labels. The workbench minimum is 10, and no judge was opted in. Until that
study exists, the gate stays on deterministic scores.
