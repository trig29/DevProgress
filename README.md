# 北四楼来信 开发进度

浅色校园笔记风格的中文静态网站，记录序章 Demo 的任务、评分、近期变化与历史。`todo.json` 是唯一维护源；网页读取从同一数据源生成的快照。没有常驻后端、数据库、登录或在线 AI 请求。

当前交付为本地预览，尚未创建 GitHub 远端或公开部署。剧情文档不公开；概括性完整 Todo、相对路径证据与验收步骤可以公开。

## 运行与检查

使用 Python 3.9 或更新版本，无需额外 Python 包或 npm 安装。项目自带的 Schema 校验器支持本项目实际使用的 JSON Schema 关键字；它不是通用的 Draft 2020-12 实现。完整 Schema 仍可由兼容编辑器读取。

```sh
python3 validate_todo.py
python3 -m unittest discover -s tests -v
python3 scripts/build_site.py
python3 scripts/preview.py
```

预览地址为 `http://127.0.0.1:4173/DevProgress/`，服务器只绑定本机，并且只提供生成目录，不提供项目源文件。停止后可用同一命令重新启动。可用 `--port` 改端口，用 `--prefix /` 检查根路径部署。

这些检查只针对进度数据和网站。禁止运行 Godot、headless、导出、游戏测试或试玩；游戏运行、视觉与音频验收由开发者完成。

## 数据与目录

| 位置 | 作用 |
| --- | --- |
| `Demo目标.md` | Demo 范围与完成条件 |
| `todo.json` / `todo.schema.json` | 完整任务、证据、规则、手动分数和结构化评估；Schema v1.1 |
| `site.config.json` | 可公开的网站名称、阶段标签和首次发布开关 |
| `config.local.json` | 本机项目与游戏路径，忽略 Git 提交和部署 |
| `web/` | 原生 HTML、CSS、JavaScript 与本地 SVG 图标 |
| `scripts/` | 校验、计算、快照生成、本地预览和发布记录工具 |
| `schemas/` | 当前快照与历史的独立 Schema v1 |
| `history/snapshots.json` | 已生成评估历史；保留当时分数与口径 |
| `site/` | 生成的静态部署产物，不手改，不提交 |
| `skills/update-dev-progress/` | 更新 skill 的可维护源码 |

生成工具输出网页、资源、`data/current.json`、`data/history.json` 和完整 `data/todo.json` 下载文件；不复制目标文档、剧情文档、本机配置或游戏文件。页面只读，展示任务、完成条件、状态和权重；完整证据、依赖与验收步骤保留在下载文件中。

## Todo 与评分口径

使用“大项 → 必要子项”两层结构：平铺 `items` 通过稳定 `id` 与 `parent_id` 关联。改名不改 ID，Todo ID 不等于 Godot 场景路径。`kind=group` 只汇总，`kind=task` 是计分叶项，`kind=manual` 对应独立手动评分。

`dimension=story/art/system/polish`；`scope=demo` 纳入当前范围，`future` 不纳入。状态 `not_started/in_progress/implemented_unverified/done` 对应未开始／进行中／实现完成待验证／已完成。未知为 `status=null`、`assessment=pending_confirmation`，不等于未开始。

**已确认规则**：剧情30%、美术与场景25%、系统15%、打磨30%。UI占美术20%（整体5个百分点）。状态档位0/40/80/100；相对权重参考小1、中3、大5，较大内容可用更多预算，不代表文件数或工时。当前规则版本 `confirmed-v1`。

```text
剧情、系统 = Σ(叶项权重 × 状态分数) / Σ叶项权重
美术与场景 = 80% × 美术自动任务加权分 + 20% × UI手动分
整体 = 30% × 剧情 + 25% × 美术与场景 + 15% × 系统 + 30% × 打磨
```

计算值保留精度，网页最后取整数百分比，贡献与变化保留一位小数。功能分支实现只展示成果，未确认集成时其目标分支计分值仍未知。规则未确认或必要任务状态／手动值未知时，相关精确分数为 `null`，显示“评估待完善”，不填零、不剔除分母、不发布估计区间。

初始手动评分由开发者提供：**UI 50%、打磨10%**。打磨贡献整体3.0个百分点；当前剧情、美术、系统和总分仍待完善。已有实现及静态证据完整保留，没有编造运行验收通过的任务。

`group_budgets` 约束叶项权重总和，不额外计分。细化保留预算、同步依赖与旧 ID 引用；扩大 Demo 须经开发者确定，更新 `scope_version`，规则调整更新 `rules_version`，并记录差值原因。父项展示状态只根据孩子汇总，不反写源数据；仅有未开始与未知孩子时不会显示“进行中”。

## 证据、评估与历史

- `evidence_ids` 关联证据；`sources` 保存当时分支、完整 commit 或目标文档。证据路径相对各自仓库。旧来源不可静默改成新 commit；新评估增加新的来源记录，保留历史证据。
- `implementation_location` 区分 `main`、`feature_branch` 或未知。只有开发者相关验收证据才能支持 `done`。
- `verification_plans` 是人工验收步骤模板。一次共享计划的部分通过不能自动推广到所有相关任务。
- `manual_scores` 数值为0～100或null，UI与打磨独立。必须记录 `updated_by=user`、带时区的更新时间及开发者来源说明。
- `evaluation` 包含评估时间、成果摘要、变化原因与各维度评价；评价解释数字，不替代计算。开发网站不能算作游戏开发成果。
- 每次有意义的变化写入 `change_log`。快照 ID 来自有效内容，同一输入重复构建、或仅修改评估时间，不新增历史。人工分数／验收变化即使游戏 commit 相同也产生新快照。
- 历史快照保留当时规则与结果，不用当前规则重算。未知趋势断开，范围／规则变化处明确分段。第一次只显示真实已知分数的单点。

本地快照 `published_at=null`。`generated_at` 是生成时间，`evaluated_at` 是评估时间。Pages artifact 在部署前记录候选发布时间，只有部署成功后访问者才会看到；本地历史的发布时间由确认线上快照后记录。网站发布不会把旧评估时间改成新评估。

## “请更新进度条” skill

源码在 `skills/update-dev-progress`，本次已安装到个人 Codex skill 目录。它允许正常自动发现，支持“请更新进度条”或显式 `$update-dev-progress`，读取本机 `location.json` 定位项目。新聊天可使用该技能；当前聊天的技能列表由宿主加载，安装后不依赖当前列表即时刷新。

日常流程：静态核对游戏提交差异 → 更新相关 Todo 与证据 → 保留人工分数／有效验收 → 生成评价、快照和历史 → 检查网页与数据 → 在已启用发布时提交、推送并核对部署结果。不会自动监听游戏 commit。

## 首次公开发布与日常授权

`.github/workflows/pages.yml` 已准备好，但 `publication.enabled=false`，未创建远端或进行部署。首次发布必须由开发者明确提出，然后将 `site.config.json.publication` 填为已确认的 `owner/DevProgress`、Pages URL并启用，配置 GitHub Pages 使用 Actions。workflow 只上传 `site/`，不是整个源仓库；所有资源路径适配项目站点子路径。

首次部署完成后，日常“请更新进度条”已授权提交相关进度文件、普通推送并等待对应 commit 的 Pages 部署成功。未启用发布时仅生成本地结果。部署失败或线上快照 ID 不匹配时不得声称网站已更新。

确认线上 `data/current.json.snapshot_id` 与本地一致后，可以运行：

```sh
python3 scripts/record_publication.py --url https://OWNER.github.io/DevProgress/
```

该步骤只记录已发布 artifact 的时间，元数据下次更新时一并提交，不制造额外开发进展。不公开本机配置、凭据、剧情正文或剧情文档；新增源文件只提交明确属于进度项目且允许公开的内容。
