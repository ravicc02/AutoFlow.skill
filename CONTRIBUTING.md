# 贡献指南 Contributing

感谢你有兴趣改进 AutoFlow!无论是指出问题、补充文档、修 bug 还是加新模块,都欢迎。

## 提问 / 报 Bug

- 先搜一下现有 [Issues](https://github.com/qiuy-collab/AutoFlow.skill/issues),避免重复
- 新建 issue 时请选择模板(bug / feature / question),并尽量给出:
  - 你使用的 Agent 客户端及版本
  - 复现步骤和最小示例
  - 实际输出 vs 期望输出

## 提交代码

1. Fork 本仓库,从 `master` 拉分支:`git checkout -b fix/xxx`
2. 改动必须配套:
   - 新模块 → 更新 `SKILL.md` 路由表与 `references/directory-layout.md`
   - 仓库内 Skill、引用、代码、配置、示例或测试变更 → 提交前更新 `CHANGELOG.md` 的 `Unreleased`，分别写清新增、变化和修复；纯运行产物不属于仓库改动
   - 逻辑改动 → 在 `tests/` 补测试
3. 本地验证:
   ```bash
   python -m unittest discover -s tests -v
   python -m compileall -q scripts tests
   ```
4. 用 `git diff --check` 和 `git diff --cached --name-only` 核对暂存内容；仅暂存本次改动，确认本次提交同时包含变更日志，再提交。不要顺手提交其他工作区改动。
5. 提交信息使用 Conventional Commits:`feat:` / `fix:` / `docs:` / `refactor:` / `test:`
6. 提 Pull Request,说明改动动机和验证结果

## 行为准则

- 保持 Schema 1.0 兼容;不引入"一键假装完成"的捷径
- 新增外部能力必须走 `integrations/` 审计流程(记录上游地址、revision、许可证和适配器),不许口头声称可用
