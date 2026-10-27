<div align="center">

<img src="display/logo/autoflow-logo.png" alt="AutoFlow Logo" width="180">

# AutoFlow

面向 Agent 的通用任务引擎。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/qiuy-collab/AutoFlow.skill/actions/workflows/ci.yml/badge.svg)](https://github.com/qiuy-collab/AutoFlow.skill/actions)

**简体中文 · [English](README.en.md)**

</div>

## Quick Start

复制下面一段发给你的 Agent：

```text
从 https://github.com/qiuy-collab/AutoFlow.skill 克隆仓库，把完整的 autoflow Skill 目录安装到本地所有 Agent 的 skills 库中（如 ~/.claude/skills/、~/.codex/skills/ 等）。

安装后阅读 references/init.md 初始化环境，然后运行 env-check 确认可用。
```

安装完成后，任务规模决定执行模式：单模块、无依赖的小交付走 direct；涉及来源选择、相互依赖、文档、打包或可恢复状态的交付走 managed。

## 本地设置

运行 `python scripts/settings_web.py`，打开终端输出的 `http://127.0.0.1:8765/`。
设置页可以修改模型与上游、批量参考图改图的模型/4K 尺寸/回退/重试、安装或删除 GitHub Skill，并显式选择 Word 编写后端。密钥只显示是否已配置，留空保存不会覆盖旧值；`.env` 与 `user_skills/` 不会进入 Git。安装仅接受 GitHub HTTPS 克隆地址，要求仓库含 `SKILL.md` 或 `skills.md`，不执行克隆仓库的脚本。Word 公共校验仍由 officecli 执行。

## 效果总览

以下全部由同一个演示项目「基于 Spring Boot + MySQL 的校园活动报名管理系统」生成。

| 填写前 | 填写后 |
| --- | --- |
| <img src="display/word/render/template-en-1.png" alt="填写前的实验报告模板" width="360"> | <img src="display/word/render/filled-en-1.png" alt="填写后的实验报告页面" width="360"> |

## Image 模块

Image 模块覆盖四种子类，以下展示全部能力。

### capture 真实浏览器截图

通过 Playwright 对本地运行的 Web 应用进行真实捕获。

```bash
python scripts/capture_frontend_screenshots.py --config <capture-plan.json> --output-dir <dir>
```

| | | |
|:---:|:---:|:---:|
| <img src="display/images/capture/01-dashboard.png" width="280" alt="dashboard"> | <img src="display/images/capture/02-activity-calendar.png" width="280" alt="calendar"> | <img src="display/images/capture/03-registration.png" width="280" alt="registration"> |
| dashboard | activity-calendar | registration |
| <img src="display/images/capture/04-operations.png" width="280" alt="operations"> | | |
| operations | | |

### AI 生图

覆盖终端命令、IDE 开发、Linux 运维和 nature-figure 科研图形摘要四类场景。

```bash
python scripts/generate_images.py --config <prompt-config.json>
```

| | | |
|:---:|:---:|:---:|
| <img src="display/images/ai/01-java-maven-terminal.png" width="280" alt="maven-terminal"> | <img src="display/images/ai/02-registration-controller-vscode.png" width="280" alt="vscode"> | <img src="display/images/ai/03-campuspulse-graphical-abstract.png" width="280" alt="graphical-abstract"> |
| Maven 构建 | VS Code 源码 | 图形摘要 |
| <img src="display/images/ai/04-linux-sql-query.png" width="280" alt="sql-query"> | <img src="display/images/ai/05-linux-network-ss.png" width="280" alt="network-ss"> | <img src="display/images/ai/06-git-commit-terminal.png" width="280" alt="git-commit"> |
| SQL 查询 | 网络验证 | Git 提交 |
| <img src="display/images/ai/07-vscode-debug-breakpoint.png" width="280" alt="debug-breakpoint"> | <img src="display/images/ai/08-browser-devtools-network.png" width="280" alt="devtools"> | <img src="display/images/ai/09-terminal-maven-test.png" width="280" alt="maven-test"> |
| VS Code 调试 | DevTools 网络面板 | Maven 测试 |

### 图表

基于 DSL 渲染，输出架构图、ER 图、流程图、类图、时序图、用例图和网络拓扑图。

```bash
python scripts/generate_diagram_assets.py --config <diagram-plan.json> --output-dir <dir>
```

| | | |
|:---:|:---:|:---:|
| <img src="display/images/diagram/campus-activity-architecture.png" width="280" alt="architecture"> | <img src="display/images/diagram/campus-activity-er.png" width="280" alt="er"> | <img src="display/images/diagram/campus-registration-flow.png" width="280" alt="flow"> |
| 系统架构 | ER 关系 | 业务流程 |
| <img src="display/images/diagram/campus-activity-class.png" width="280" alt="class"> | <img src="display/images/diagram/campus-registration-sequence.png" width="280" alt="sequence"> | <img src="display/images/diagram/campus-system-usecase.png" width="280" alt="usecase"> |
| 类图 | 时序图 | 用例图 |
| <img src="display/images/diagram/campus-network-topology.png" width="280" alt="topology"> | | |
| 部署拓扑 | | |

### chart 数据图表

基于 nature-figure 出版级图表模板，支持火山图、ROC 曲线、点图、边缘分布图等。

```bash
python integrations/nature-figure/scripts/plot_templates.py <template> ...
```

| | | |
|:---:|:---:|:---:|
| <img src="display/images/chart/activity-metric-matrix.png" width="280" alt="metric-matrix"> | <img src="display/images/chart/capacity-vs-registration.png" width="280" alt="capacity"> | <img src="display/images/chart/activity-volcano.png" width="280" alt="volcano"> |
| 指标矩阵 | 容量对比 | 火山图 |
| <img src="display/images/chart/checkin-model-roc.png" width="280" alt="roc"> | <img src="display/images/chart/activity-category-dotplot.png" width="280" alt="dotplot"> | <img src="display/images/chart/registration-marginal.png" width="280" alt="marginal"> |
| ROC 曲线 | 类别点图 | 边缘分布 |

## Office 模块

### Word 模板填写

Reading the report template, filling each section with real project evidence, validating via officecli, and rendering page by page.

```bash
python scripts/office_engine.py --action fill --format word ...
python scripts/validate_office.py <file>.docx
```

| Page 1 | Page 2 |
|:---:|:---:|
| <img src="display/word/render/filled-en-1.png" width="280" alt="filled-en-1"> | <img src="display/word/render/filled-en-2.png" width="280" alt="filled-en-2"> |

### Word 从零创建

Creating a graduation thesis from scratch with abstract, chapters, and results, validated page by page via officecli.

| Page 1 | Page 2 |
|:---:|:---:|
| <img src="display/document-from-scratch/render/thesis-en-1.png" width="280" alt="thesis-en-1"> | <img src="display/document-from-scratch/render/thesis-en-2.png" width="280" alt="thesis-en-2"> |
| Page 3 | Page 4 |
| <img src="display/document-from-scratch/render/thesis-en-3.png" width="280" alt="thesis-en-3"> | <img src="display/document-from-scratch/render/thesis-en-4.png" width="280" alt="thesis-en-4"> |

## 链路总览

```mermaid
flowchart LR
    R[用户请求] --> Q{单模块、低风险、无依赖?}
    Q -->|是| D[direct: 初始化工作区与 submit/]
    D --> DA[执行并校验最小交付]
    Q -->|否| M[managed: 初始化 DAG]
    M --> P[PLAN STOP]
    P --> T[task / GitHub 来源]
    T --> S[SOURCE STOP]
    S --> I[image / office / video]
    I --> V[VISUAL STOP]
    V --> K[package 与验收]
    K --> L[DELIVERY STOP]
```

## 五个模块速查

| 模块 | 用途 |
| --- | --- |
| `task` | GitHub-first 检索、项目构建、计算和可运行性证据。 |
| `image` | 真实捕获、AI 生成电脑截图、确定性图和基于真实数据的图表。 |
| `office` | Word、PPT、Excel 的创建、填充、渲染审查和计划级校验。 |
| `video` | 既有视频分析、录制、生成和处理。 |
| `package` | 依据需求组装干净的 `submit/` 交付目录与可验证清单。 |

## 插件

AutoFlow 默认内置以下四个插件，用户可自行添加更多：

| 插件 | 用途 |
| --- | --- |
| `officecli` | Office 文档的结构化编辑、OpenXML 校验和 HTML 渲染。 |
| `minimax-docx` | 复杂 Word 报告/论文创建与填充后端；由 Agent 按任务选择，仍由 `officecli` 校验和渲染。 |
| `impeccable` | 前端设计语言与离线质量检测适配。 |
| `nature-figure` | 具有数据来源和质量记录的出版级图表模板。 |

## 赞助商

[sshzyu.com](https://sshzyu.com) 提供 AI 生图功能 API。

## 常见问题

- `capabilities` 显示缺失：先按 [环境初始化](references/init.md) 安装对应依赖，再重新检查。
- AI 路由被阻塞：仅由用户配置 `.env` 的 `BASEURL`、`APIKEY` 和可选 `VALIDATOR_*`；不要伪造图片。
- 浏览器截图失败：确认本地应用可访问，安装 `playwright` 后执行 `python -m playwright install chromium`。
- Mermaid 或 D2 不可用：安装对应 CLI，并用 `autoflow.py capabilities --json` 确认渲染器已被识别。
- Office 校验失败：用 `officecli validate` 和 `officecli view <file> issues --json` 定位问题，再运行 `office_engine.py` 与 `validate_office.py`。
- 工作流拒绝完成节点：检查每个声明产物的绝对路径和哈希；修改已登记产物时先运行 `autoflow.py revise`。
- `submit/` 被拒绝：移除构建输出、缓存、编辑器元数据、密钥和 AutoFlow 运行元数据，只保留最终交付物。

## 测试

```bash
python -m unittest discover -s tests
```

## License

[MIT](LICENSE) © [qiuy-collab](https://github.com/qiuy-collab)
