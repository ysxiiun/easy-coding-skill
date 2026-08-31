# Git 纪律

> 仅在任务涉及 Git 拉取、合并、暂存、提交、推送、发布或跨仓交付时读取。Git 操作不改变
> Easy Coding 阶段与 QUALITY 门禁。

## 1. 范围

- 默认纳入与任务相关的共享 `.easy-coding` 项目知识与记忆文件。
- 永不提交 `.easy-coding/sessions/`、Harness tasks、平台配置、install manifest 或其他私有层。
- `.easy-coding/spec/dev/` 是当前需求候选输入，只有用户明确要求提交时才纳入；Canonical
  locator 位于该目录时同样适用本例外，不能因 execution 受控写回而自动暂存。
- 提交前逐项核对 QUALITY candidate、机器 ignore 和 `git status`；不得混入预存无关改动。
- 未获用户明确授权时不提交、不推送、不发布。

## 2. 冲突

`.easy-coding/` 内发生合并、变基或拣选冲突时必须暂停：

1. 列出冲突文件、双方语义和与当前任务的关系；
2. 给出归纳式合并方案，不以单边覆盖代替理解；
3. 获得用户确认后才编辑并标记解决；
4. 重新执行受影响 QUALITY 检查。

该确认只针对共享目录冲突，不替代提交/推送授权。

## 3. 跨仓与子模块

- 多仓候选分别保留 repo ID、HEAD、scope 和验证证据。
- 父仓存在脏 gitlink 或任务会修改 submodule 时，父仓与子仓都必须作为独立质量 repo；只用
  父仓指纹不能证明子仓内容未漂移。
- 先在子仓完成代码、QUALITY、提交与远端交付；再回父仓更新 gitlink。
- 父仓提交前验证子仓指针就是已交付远端 SHA，不能指向仅本地提交。
- 依赖仓交付失败时不得推进父 gitlink。

## 4. 提交与推送证明

用户要求“提交推送”时，完成标准同时包括：

1. scope audit 与一致的 staged 集合；
2. coherent commit 和目标远端/分支 push 成功；
3. 本地 HEAD 与远端目标 SHA 完全一致；
4. ahead/behind 为 `0/0`；
5. 最终 `git status` 无本任务残留，并明确披露保留的预存无关改动。

只报告本地 commit、仅有基线 `0/0` 或未核对远端 SHA 都不算交付完成。
