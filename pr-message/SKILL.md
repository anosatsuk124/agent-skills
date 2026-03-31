---
name: pr-message
description: >-
  Generate a comprehensive pull request message by analyzing git diffs between
  the current branch and a target base branch. Use this skill when the user asks
  to "generate a PR message", "write a PR description", "create a pull request
  summary", "draft PR notes", "summarize my changes for a PR", or wants help
  writing a pull request description based on their branch changes. Also trigger
  when the user mentions "PR message", "PR description", "pull request body", or
  wants to review and summarize what changed on their branch before opening a PR.
  Even if the user just says "what should I write for this PR" or "help me
  describe these changes", this skill applies.
argument-hint: "[target-branch]"
allowed-tools:
  - Read
  - Write
  - Bash(git:*)
  - Bash(mkdir:*)
  - Bash(date:*)
---

# PR Message Generator

Generate a comprehensive, well-structured pull request message by analyzing all
changes between the current branch and a target base branch, then save it as a
markdown file under `./.tmp/`.

## Step 1: Determine the Base Branch

The user may provide a target branch as an argument: `$ARGUMENTS`

If a target branch argument is provided and non-empty, use it as the base branch.
Otherwise, auto-detect the default branch:

```bash
git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@'
```

If that fails (no remote configured), fall back to checking which exists locally:
- Try `main` first: `git show-ref --verify --quiet refs/heads/main`
- Then try `master`: `git show-ref --verify --quiet refs/heads/master`

Store the resolved branch name for all subsequent commands.

## Step 2: Validate the Branch State

Before gathering data, confirm there are actual changes to describe:

1. Verify the base branch exists (locally or as a remote tracking branch)
2. Confirm the current branch has commits diverging from the base:
   `git rev-list --count <base>..HEAD`
3. If there are zero commits ahead (branches are identical), inform the user
   and stop — there is nothing to generate a PR message for

## Step 3: Gather Comprehensive Diff Information

Collect three pieces of information. Read the **full output** of each command —
do not truncate or skip any of it. Even small changes provide important context.

### 3a. Commit history

```bash
git log <base>..HEAD --format="%h %s" --reverse
```

The `--reverse` flag shows commits in chronological order, revealing how the
work progressed and what the developer intended at each step.

### 3b. File change summary

```bash
git diff <base>...HEAD --stat
```

This provides the high-level picture of which files changed and how extensively.

### 3c. Full diff

```bash
git diff <base>...HEAD
```

Read the entire diff. If the diff is very large (over 10,000 lines), read it in
chunks but ensure every file's changes are accounted for in the final PR message.

**Important syntax note:**
- Use three-dot (`...`) for `git diff` to show only changes introduced on the
  current branch since it diverged from the base
- Use two-dot (`..`) for `git log` to show commits on the current branch that
  are not on the base

## Step 4: Analyze the Changes

Before writing the PR message, think through the changes:

1. **Overall purpose** — What problem does this branch solve or what feature
   does it add? The commit messages and totality of changes should tell a story.

2. **Related changes** — Group changes that belong together. A rename in one
   file and a corresponding import change in another are part of the same
   logical change.

3. **Architectural decisions** — New files, deleted files, significant refactors,
   new dependencies — these deserve specific callouts.

4. **Breaking changes** — Removed public APIs, changed function signatures,
   modified configuration formats, database migrations, or anything requiring
   other code or users to adapt.

5. **Reviewer focus areas** — Complex logic, tricky edge cases,
   performance-sensitive code, security-relevant changes.

6. **Scope boundaries** — What was intentionally NOT changed that someone might
   expect? Sometimes the absence of a change is worth noting (e.g., "This PR
   does not migrate existing data; that will be a follow-up").

## Step 5: Generate the PR Message

Write the PR message in **Japanese keigo (polite/formal Japanese, です・ます調)**.
Use this structure. Adapt sections based on relevance —
skip sections that do not apply (e.g., omit Breaking Changes if there are none).
The goal is a message that gives a reviewer everything they need to understand
and review the PR quickly.

### Template

```markdown
# <タイトル: 簡潔な要約、最大約72文字>

## 概要

<このPRが何をするものか、なぜ必要かを2〜4文で説明してください。
このセクションだけを読んだレビュアーがPRの目的を理解できるようにしてください。>

## 背景・動機

<なぜこの変更が必要なのかを説明してください。関連するissue番号、ユーザー報告、
ビジネス上の背景があれば言及してください。コードのみから動機を判断できない場合は、
推測できる範囲を記載し、著者に追記を促してください。>

## 主な変更点

<変更内容を論理的にグループ化した箇条書きで説明してください。
ファイル名だけでなく、何が・なぜ変更されたかを簡潔に記載してください。>

- **<領域・コンポーネント>**: <変更内容の説明>
- **<領域・コンポーネント>**: <変更内容の説明>

## テストについて

<変更の検証方法をチェックボックス形式で記載してください。
新規・変更されたテストや手動テストの手順を以下のように列挙してください。
テスト方針がdiffから読み取れない場合は、著者への追記提案もチェックボックスとして記載してください。>

- [ ] <テスト項目1>
- [ ] <テスト項目2>

## 破壊的変更

<該当する場合のみ記載してください。何が壊れるか、誰が影響を受けるか、
対応のために何をする必要があるかを説明してください。>
```

### Writing Guidelines

- **具体的に記述すること。**「決済バリデーションを `PaymentValidator` に切り出し、
  Stripe APIなしのユニットテストを可能にしました」のように、何をなぜ変えたかを明確にしてください。
- **コミット履歴を活用すること。** コミットが物語を語っている場合（リファクタ→機能追加→
  エッジケース対応の順など）、PRメッセージもその流れに沿って書いてください。
- **数字は控えめに。** 行数などの数値よりも、変更の意味を重視してください。
- **不確かな点はフラグを立てること。**「著者に意図を確認することをお勧めします」と
  記載する方が、誤った推測をするよりも適切です。
- **日本語の敬語（です・ます調）で統一すること。** 技術用語（JWT, API, Bearer token等）は
  英語表記のまま使用してください。

## Step 6: Save the PR Message

1. Create the output directory if it does not exist:
   ```bash
   mkdir -p ./.tmp
   ```

2. Generate a unique filename using the branch name and a timestamp:
   ```bash
   git branch --show-current
   date +%Y%m%d-%H%M%S
   ```

3. Combine into: `./.tmp/pr-message-<branch-name>-<timestamp>.md`
   - Sanitize the branch name by replacing `/` with `-` for a valid filename

4. Write the generated PR message to this file.

## Step 7: Present the Result

After saving:

1. Display the full PR message content so the user can read it immediately
2. Tell the user where the file was saved (relative path), in Japanese keigo
3. Ask in Japanese keigo if they want any adjustments — tone, detail level, sections to add/remove

## Edge Cases

- **Merge commits:** If the branch has merge commits from the base, focus the
  PR message on the author's changes, not merged-in upstream changes. The
  three-dot diff syntax helps with this.
- **Binary files:** Note their presence but do not describe binary diffs.
  Mention what the binary files are (images, compiled assets, etc.).
- **Very large PRs (50+ files):** Group changes by directory or module. Consider
  suggesting the author split the PR if the changes are clearly unrelated.
- **Minimal changes:** If the diff is only whitespace, formatting, or
  auto-generated code, say so directly rather than inflating the description.
- **Detached HEAD:** If on a detached HEAD (no branch name), use `HEAD` with
  the short commit hash for the filename instead of a branch name.
