# Worktree Guide

当前仓库已经预建了 3 个 Git worktree，方便多线程或多 agent 并行开发：

- `main` 主仓库：
  [bilibili-topic-kb-builder-git](/D:/UnrealGit/Skills/unreal-source-analyzer/bilibili-topic-kb-builder-git)
- 重试优化分支：
  [bili-kb-retry-optimization](/D:/UnrealGit/Skills/worktrees/bili-kb-retry-optimization)
- 网页展示分支：
  [bili-kb-web-viewer](/D:/UnrealGit/Skills/worktrees/bili-kb-web-viewer)
- 文档与 Skill 分支：
  [bili-kb-docs-skill](/D:/UnrealGit/Skills/worktrees/bili-kb-docs-skill)

对应分支：

- `main`
- `codex/retry-optimization`
- `codex/web-viewer-upgrade`
- `codex/docs-skill`

建议规则：

- 一个 Codex 线程只使用一个 worktree
- 不同线程不要同时改同一个 worktree
- 功能完成后，在对应 worktree 内提交、推送、开 PR
- 合并后回主仓库更新 `main`

常用命令：

```bash
git worktree list
git -C D:/UnrealGit/Skills/worktrees/bili-kb-retry-optimization status
git -C D:/UnrealGit/Skills/worktrees/bili-kb-web-viewer status
git -C D:/UnrealGit/Skills/worktrees/bili-kb-docs-skill status
```
