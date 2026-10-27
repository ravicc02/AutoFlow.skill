# Changelog

本项目的版本说明遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的结构。

## [Unreleased]

### Added

- 新增仅本机监听的 Web 设置页：模型与密钥配置、批量参考图编辑默认模型/尺寸/回退模型/重试次数、GitHub HTTPS 技能包安装/删除/文件探测、Word 编写技能选择。现有密钥只显示配置状态，空白提交不覆盖；用户包存放于被 Git 忽略的 `user_skills/`。
- 新增配置与 Web 安全测试，覆盖密钥遮蔽、请求来源校验、GitHub 克隆地址限制、受管包删除边界、改图回退以及显式 Word 选择不可用时的阻断。

- 新增 `references/image-parameter-matrix.md`：记录配置上游的 1K/2K/4K × 8 种宽高比对应的 24 个像素尺寸，并规定批量生图的 `4K + auto` 选择顺序、用户显式比例优先及上游拒绝尺寸时不得静默替换。
- 新增 `scripts/image_size.py` 与生图测试：按参考图比例或素材类型解析自动宽高比，覆盖完整矩阵、旧像素尺寸兼容、显式比例冲突及批量默认值。
- 固化仓库维护流程：修改 Skill、引用、代码、配置或测试时，在提交前同步更新 `CHANGELOG.md` 的 `Unreleased`，验证并核对暂存内容；普通 AutoFlow 任务的运行产物不触发仓库变更日志。

- 新增 `integrations/` 包契约（manifest 2.0）：每个包声明 `type`（tool/knowledge-only）、`capabilities`（能力名列表）、`check` 入口（仅探测本地运行条件）；核心层 `IntegrationRegistry` 自动发现所有包，`integration_catalog()` 依赖注册表输出，不再硬编码 detect 函数。
- 新增 `integrations/officecli/` 包：officecli 官方 SKILL.md 迁入集成目录，manifest 声明 `role: engine` + 三个 office 能力，check 脚本探测本机二进制版本。
- 新增 `integrations/nature-figure/scripts/check.py` 与 `integrations/impeccable/scripts/check.py`：分别探测 Python 依赖和 Node.js 可用性（manifest 2.0 升级）。
- 新增 `references/integration-contract.md` 文档（旧版从 `integration_manifest.json` 契约更新为 2.0 合约）。
- 新增注册表单元测试：missing/invalid manifest、check 运行、knowledge-only 包语义。
- 新增 `references/init.md`：环境初始化提示词驱动的唯一入口（client-neutral），供 Agent 在任意客户端按需检查/安装所选能力环境。
- 新增浏览器截图 `capture_scope`（viewport/selector/page）与跨平台浏览器检测（PATH 查找 + `AUTOFLOW_BROWSER_PATH`）：一块完整看板可超出单视口高度，不再用长图拼接多个独立看板；视觉审查清单新增规则 8/9，配套 `tests/test_capture_frontend_screenshots.py`。

### Changed

- 批量 `reference_image` 任务使用独立的改图默认参数；主模型按配置次数尝试失败后才启用回退模型，并在结果中记录实际模型。Word 路由将所选 Skill 的路径和 `authoring_skill` 返回给 Agent，保留 officecli 公共校验，不再为显式指定的 Word 技能静默降级。

- 批量 AI 生图默认使用 `4K` 档与 `aspect_ratio: auto`，发送到上游前解析为矩阵中的具体 `size`；参考图优先保持接近原图的比例，截图/UI 默认为 16:9，其余素材默认为 1:1。任务或单图可显式覆盖，旧 `WIDTHxHEIGHT` 值保留原样。
- `SKILL.md`、`modules/image.md`、提示词规则、配置模板及 `.env.example` 指向统一矩阵；2K 16:9 改按矩阵使用 `2560x1440`，不再把旧 `2048x1152` 标为该档预设。
- 生图结构校验接受 4K/2K/1K 与自动比例组合，覆盖所有矩阵比例并拒绝显式像素与比例冲突；生成报告记录解析后的尺寸和比例，环境报告的批量默认尺寸同步为 4K。

- Office 采用可选第三方后端路由：`minimaxdocx`/`minimax-docx` 处理复杂 Word 报告与论文，`officecli` 继续负责通用检查、校验、渲染以及 PPT/Excel；缺运行时明确 blocked，不静默降级。相关模块、初始化说明、填充规则、故障表与 README 已同步。
- Office 默认路由不依赖 `.env` 锁定或本机 Skill 路径：`integrations/minimax-docx` 成为复杂 Word 默认可选包；本次设置页进一步加入可选的 `WORD_AUTHORING_SKILL` 显式覆盖。`.env` 不保存第三方包路径。
- `integrations/` 架构从"被审查的文件拷贝"升级为"插件化能力包仓库"：AutoFlow 只做三件事（发现、校验 check、分发），用法知识留在包内 SKILL.md，agent 自行阅读；AutoFlow 不再重写第三方用法或提供 adapter 封装。
- `scripts/impeccable_adapter.mjs` 移入 `integrations/impeccable/scripts/`（作为包内离线入口），包内文档的引用自动适配；`AUTOFLOW_ADAPTER.md` 删除。
- `detect_impeccable_backend()` 从硬编码文件列表改为注册表查询（`integration_catalog` 过滤），输出保持 `status/backend/integration_root/skill_file/runtime` 兼容。
- `detect_office_backend()` 的 `integration_root` 指向 `integrations/officecli/`。
- 模块文档改写为纯分发语义：`modules/image.md`（Frontend visual quality → 读包内 SKILL.md；Publication charts → 用法在包内）、`modules/task.md`（impeccable 段指向包内文档）、`modules/office.md`（官方手册在包内，本模块只提炼关键约束）、`modules/office/{word,ppt,excel}.md`（指向包内官方手册）。
- 测试：`test_autoflow_core.py` 的 catalog 断言更新为 3 个包 + 新字段（type/capabilities/check_status/role），移除旧字段（self_contained/mode/external_user_skill_required/source_checkout_required）；`test_autoflow_cli.py` 的 integrations 命令断言同步；`test_backend_cli.py` 的 adapter 路径更新为 `integrations/impeccable/scripts/impeccable_adapter.mjs`。
- 环境初始化从脚本驱动改为提示词驱动：`task.environment` 报告的 `command` 只接受 `agent-init`；direct mode 要求初始化任务工作区（`.autoflow/intermediate`、`.autoflow/runtime`、`submit/`）并在 `submit/` 下交付。SKILL.md、README、modules 与 references 的相关引用全部改指 `references/init.md`。
- 图片提示词质检 API 配置从 `AGNES_*` 通用化为 `VALIDATOR_BASEURL`/`VALIDATOR_APIKEY`/`VALIDATOR_MODEL`：任意 OpenAI 兼容端点均可作为质检上游，供应商与模型由用户自配；三项缺一时 `validate_prompt.py` 明确报错，不再内置默认模型名。
- `docs/prompts/docx_fill_rules.md` 新增排版与填充效果章节：文本质量、间距与填充位置、字号层级、行距留白、标题层级、中文字体与全半角标点、图注格式、整体规整性——全部为原则级约束，跟随模板既有体系，不引入凭空数值。

### Removed

- 删除 `integrations/impeccable/AUTOFLOW_ADAPTER.md`（adapter 模式已废弃）。
- 删除 `integrations/impeccable/integration_manifest.json` 与 `integrations/nature-figure/integration_manifest.json`（1.0 旧契约，以 `manifest.json` 2.0 取代）。
- 删除 `scripts/env_check.ps1`、`scripts/environment_setup.py` 与 `tests/test_environment_setup.py`：脚本驱动环境初始化退役，由 `references/init.md` 提示词驱动流程取代。
- 删除 `docs/prompts/visual_review_rules.md`：视觉审查已定为纯人工决策（VISUAL_STOP human-only），不存在 AI 审查读者；其中 capture_scope 看板边界规则已在 `modules/image.md` 完整覆盖。
- 新增 `autoflow.py direct-route` 与 `autoflow.py review`，分别用于轻量本地能力路由和四类 STOP 审核信息包。

### Changed

- `submit/` 只接受可直接交付的最终内容：`package_submission.py` 新增硬拒绝——编译产物（`dist`/`build`/`target`/`out`/`bin`/`obj`/`.next`/`.gradle`/`.idea`/`.vscode`/`coverage` 等目录与 `*.exe`/`*.dll`/`*.so`/`*.class` 等后缀）与 AutoFlow 运行元数据（`manifest.json`、`*_manifest.json`、`workflow.json`、`artifact_manifest.json`、`run_state.json` 等）；`--verify-only` 的 `no_sensitive_files` 检查扩展到已发布文件夹（原先只查 zip），并在结果中输出 `forbidden` 明细。
- 打包 manifest（`autoflow/package-manifest/1.0`）从 `submit/` 移到 `.autoflow/intermediate/plans/`（运行受管区，不再混入交付内容）；`validate_package_acceptance` 相应豁免 `package.manifest` 的 submit 位置约束，bundle/zip/folder 仍必须在 `submit/` 下。
- 图片验收为纯人工决策：删除 `check_images.py`（AI 视觉预检），任何路由、任何内容生成的图片都不做 AI/自动预检，生成后直接进入人工 `VISUAL_STOP` 审核；`modules/image.md` 同步移除 pre-check 指引。
- `init` 的 `--output-dir` 改为可选：缺省时 run 锚定到 request 文件所在目录（任务项目根），不再落在会话工作区根目录；显式传参仍可覆盖。SKILL.md 与 `references/directory-layout.md` 同步更新。
- 文档操作统一为 `office` 模块：`modules/office.md` 统一入口，按 `format` 分发 word/ppt/excel 子模块；产物统一为 `office.document` + `office.validation`，验证器统一为 `office_acceptance`。
- Word/PPT 处理后端从内嵌 .NET/pptxgenjs 集成重构为 `officecli` 二进制驱动（`scripts/office_engine.py` + `scripts/validate_office.py`），支持 docx/pptx/xlsx 三格式，能力检测为 `detect_office_backend`。
- 移除 `integrations/minimax-docx` 与 `integrations/presentation-skill`，集成目录只保留仍在使用的集成。
- 移除 `integrations/superpowers`、`integrations/webapp-testing`、`integrations/agent-skills`、`integrations/engineering-quality` 四个方法论/浏览器集成：路由不再注入外部方法论 Skill（`skill_names`/`global_skill_names` 清空，仅保留本地的 `impeccable` 绑定），`validate_capabilities` 删除对应硬门禁，`image.capture` 路由内联为本地 Playwright 检测（`capture_frontend_screenshots.py`），删除 `scripts/engineering_quality_adapter.py` 与 `env_setup.py`/`env_check.ps1` 中的对应路径项；集成目录仅剩 `nature-figure` 与 `impeccable`。
- 多 office 步骤（如 word + ppt 双分支 recipe）允许共享 `office.document`/`office.validation` 产物声明，manifest 按 producer 区分登记。
- 显式调用 AutoFlow 不再强制进入 Managed mode；只有依赖、多模块、源码选型、打包、复杂证据或重要决策才使用完整 DAG。
- PLAN、SOURCE、VISUAL、DELIVERY 请求确认前必须展示对应计划、候选、实际视觉产物或交付清单及绝对路径。
- Direct mode 默认最小交付，不再为一张图附带无必要的控制文件、多个导出格式和签收流程。

## [3.1.0] - 2026-07-17

### Added

- 新增 `task`、`image`、`word`、`ppt`、`video`、`package` 六模块组合架构，以及可扩展的 recipe DAG。
- 新增 PLAN、SOURCE、VISUAL、DELIVERY 四类人工确认点，并持久化步骤、审批和产物状态。
- 代码和项目任务增加 GitHub-first 源码发现、候选评分、revision 固定和无候选 fallback。
- 内置 minimax-docx、nature-figure、presentation-skill、webapp-testing、impeccable、superpowers、agent-skills 和 engineering-quality，运行时不再依赖设备上碰巧安装的同名 Skill。
- 新增科研图、任意图示、AI 图片、网页截图、Word/PPT/视频验证与交付包检查能力。
- 增加需求到证据的映射、产物 SHA-256、隔离复测、运行耗时统计和缓存复用。

### Changed

- 项目由固定实验报告流程改为通用多产物工作流，并由 AutoLab 更名为 AutoFlow。
- 运行目录统一为 `autoflow/.autoflow/` 与 `autoflow/submit/`，中间文件不再混入交付目录。
- 环境准备改为模块级强制协议：先自动补齐，失败后尝试安装，并把结果写入可验证报告。
- Word 与 PPT 使用仓库内经过审计的本地内核；AI 图片使用 AutoFlow 自身 `.env` 中配置的上游。
- 最终源码采用“隔离复测 → 最后打包 → 只读校验”的顺序，避免复测污染 `submit/`。

### Fixed

- 修复深层 `.git` 等敏感目录可能进入交付包的问题。
- 修复已完成步骤的产物变化后无法正式重开和追踪 revision 的问题。
- 修复图片能力测试只覆盖单一 diagram 类型的问题，补齐 diagram 与 nature-figure 分类和全路线测试。
- 减少重复渲染、重复哈希和不必要的串行步骤，缩短完整工作流耗时。

### Breaking

- AutoFlow Schema 1.0 不兼容旧版 AutoLab `workflow.json`；旧任务需要重新执行 `autoflow init`。

[3.1.0]: https://github.com/qiuy-collab/AutoFlow.skill/releases/tag/v3.1.0
