---
name: update-dev-progress
description: 更新“北四楼来信”的 Demo 开发进度。当开发者说“请更新进度条”、提交人工评分或游戏验收结果、补充进度 Todo 时，静态读取游戏仓库并维护 DevProgress 的任务、评估、网站快照与历史。首次公开发布完成后，日常更新包括提交、推送与检查部署。不要用于游戏代码修改或运行游戏。
---

# 更新北四楼来信开发进度

## 找到项目与当前规则

在当前 DevProgress 工作区读取 `config.local.json`；若当前聊天不在该工作区，读取本 skill 目录的 `location.json` 获取 `progress_project`，再读取该项目的 `config.local.json` 获取 `game_repository`。这些文件是本机配置，不公开、不写入网站。未找到时询问项目位置，不另建项目。

读取游戏仓库 `AGENTS.md`、进度项目的 `Demo目标.md`、`README.md`、`todo.json`、`site.config.json` 和最近历史快照。`todo.json` 是唯一维护源；公开快照与网页由工具生成，不能直接手改分数。项目使用原生静态网页与本地 Python 工具，不创建服务器、数据库或在线 AI 接口。

开发者已确认剧情/美术/系统/打磨占整体 30/25/15/30，UI 占美术 20%，任务状态档位 0/40/80/100；以项目中当前已确认版本为准。UI、打磨由开发者分别评分，保留原值；未知不是零，不按文件数、行数或提交数计分。

## 静态评估与维护

- 记录游戏目标分支的完整 commit 与工作区状态，按上次基线至本次 commit 的差异读取相关脚本、资源、引用和状态逻辑。首次基线或范围发生重大变化时全面核对；普通更新聚焦受影响任务及必要依赖。
- **禁止运行 Godot、headless、导出、游戏测试或试玩。** 游戏仓库只读。网页和进度工具的独立测试可运行。运行、视觉、音频结论由开发者提供，输出简短验收步骤和预期结果。
- 正式公开快照对应已提交的游戏基线。未提交内容只作为本地待确认记录；如需读取提交版本，可使用 `git show <commit>:<path>`，不得把工作区内容冒充 commit 证据。工具拒绝发布 `dirty=true` 的正式来源；不要为了绕过校验伪造 clean 状态。
- 根据稳定任务 ID 更新状态与证据。存在实现但尚有必要缺口为 `in_progress`；实现完整而未验证为 `implemented_unverified`；未知用 `status=null` / `assessment=pending_confirmation`。功能分支证据标记 `feature_branch`，不当作 main 已集成。小游戏不自动增加关卡、局内存档或主线前置需求。
- 只有开发者明确的相关验收证据才能将行为、视觉或音频任务标为 `done`。保留仍有效的旧验收；相关代码变更可能使其失效时明确复核。不能把一次共享验收计划的部分通过扩散到所有任务。
- 每次新增证据对应不可变的来源 ID、实际 commit 与相对路径；保留旧来源、证据及 commit，不改旧来源的 commit 来伪装旧验收针对新代码。新增 `sources` 时用 `kind=git`、`repository`、`ref`、完整 `commit` 和实际 `dirty`。目标文档是范围依据，不是游戏功能完成证据。
- 新 Todo 区分已有目标细化、Demo扩大范围、后续版本。细化保持 `group_budgets` 总预算和两层结构，更新旧引用；扩大 Demo 或改变评分规则须有开发者决定，更新对应版本并解释差值。尚未决定的需求放 `candidate_notes`，后续任务用 `scope=future`。支线角色与主题、序章段落未定时保留设计任务，不编造剧情。

## 评估记录、导出与检查

在 `todo.json.evaluation` 写入带时区的 `evaluated_at`、3～5 条有证据支持的 `highlights`、对应 `change_reasons` 和四维度简短 `dimension_reviews`。评价解释已有计算口径和主要剩余工作，不代替算分，不把网站建设算成游戏进展。`change_reasons.type` 使用当前 Schema 枚举。同步 `snapshot` 的日期、范围/规则版本、基线来源及有意义的 `change_log`。

运行进度项目命令：

```sh
python3 validate_todo.py
python3 -m unittest discover -s tests -v
python3 scripts/build_site.py
```

若系统 Python 缺少运行所需能力，使用 Codex bundled Python；项目工具不需要额外 Python 包。生成物在 `site/`，历史在 `history/snapshots.json`。不要人工调整历史分数；相同有效输入不新增记录，仅更新时间不算进展。生成失败时先修复原因，不发布残缺产物。

手动分数变化时，记录 `updated_by=user`、带时区的 `updated_at` 和开发者原始说明。若只是评分/验收变化，即使游戏 commit 相同也可新增快照。数字未知显示待完善，不擅自生成估计区间。

## 发布授权与结果

开发者已约定：**首次公开部署完成后**，日常“请更新进度条”默认授权更新本项目、提交相关文件、推送既有进度仓库并等待 Pages 部署结果。本次首次交付只要求本地预览，不能据此创建远端、公开发布或修改游戏仓库。

检查 `site.config.json.publication`。`enabled=false` 或缺少已确认仓库/URL 时仅生成本地结果，报告尚未公开。首次公开发布只有在开发者明确要求后才能配置独立公开 `DevProgress` 仓库、既有 Pages workflow 和授权标记；不得推送到游戏仓库，不额外建立项目。

已启用发布时，核对 Git remote 与配置中进度仓库一致，查看工作区和暂存区，只提交本次进度相关文件，保留其他未授权改动。标准流程是校验/生成、提交相关数据与历史、普通推送，然后等该 commit 的 Pages workflow 成功并确认线上 `data/current.json.snapshot_id` 与本地一致。不得 force push 或把已有暂存改动混入提交。

部署 artifact 的时间由 `scripts/stamp_deployment.py` 标记，只有成功部署的网页才会展示。确认线上快照后可用 `python3 scripts/record_publication.py --url <已确认的Pages地址>` 记录历史发布时间；该元数据下次更新时一并提交，不为它再造进展快照。部署失败或快照不匹配明确报告并停止发布重试循环，保留本地成果，不声称网站已更新。

最终报告：整体/维度分数或缺失原因、主要变化和原因、主要剩余工作、待人工验收事项，以及本地或已发布状态。未知差值不写零。公开 JSON 可以包含完整概括性 Todo 与静态证据；剧情正文/文档、本机绝对路径和凭据不得进入公开文件或 Git 历史。
