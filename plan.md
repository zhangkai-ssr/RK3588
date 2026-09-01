# RK3588 工作记录

本文件是 APRK3588 跨工作区的人机协作记录。详细差异、命令输出和提交内容以 `git log` 为准；每项工作只保留范围、验证摘要和提交/合并标识。

## 记录规则

1. 直接在 `main` 完成的工作写 `direct`；在 `.WORKTREE/` 完成的工作写 `worktree`，并记录分支名和相对路径。
2. `工作范围` 只写用户可理解的目标和受影响模块，不重复文件清单；`验证摘要` 只写实际完成的静态、回环、部署或真机证据。
3. 未提交或未合入的工作写“进行中”或“待合入”；提交/合并后补齐短提交号或 PR/merge 标识并更新状态。
4. 记录随当前提交首次创建时，`提交/合并` 可写“本提交”。保留分支或 PR 时不删除历史记录。

## 工作记录

| 日期 | 方式 | 工作区/分支 | 工作范围 | 验证摘要 | 提交/合并 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-09-01 | direct | `main` | 将现有 RK3588 资料、Orange Pi 部署内容和 `sensor_host` 建立为根 Git 仓库，并配置项目入口、忽略规则和 Git LFS。 | 本地、`origin/main` 与远端提交一致；216 个受控文件、27 条 LFS 路径且无待上传对象；协议构包自检通过。 | `cffca35` | 已完成 |
| 2026-09-01 | worktree | `feature/rk3588/agents-plan-adaptation` / `.WORKTREE/agents-plan-adaptation/` | 接入并适配 RK3588 根级协作规则和统一工作记录，补充 README 入口。 | 3 份 Markdown 相对链接、`git diff --check`、`.WORKTREE/` 忽略、16 个 Python 模块编译、EMG/IMU 构包、4 个 PowerShell 与 6 个 Shell 脚本语法检查通过；PR 前后自审 Critical/Important/Minor 均为 0，GitHub 未配置 checks；未执行部署或真机操作。 | PR #1 / merge `154c0e7` | 已完成 |
