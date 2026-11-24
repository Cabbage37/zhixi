---
name: skill-workshop
description: 根据用户给定的任务、样例、约束创建或修订可移植的 SKILL.md，并以文字样例验证技能行为。
---

基于 [OpenAI Skill Creator](https://github.com/openai/skills/blob/main/skills/.system/skill-creator/SKILL.md) 的元数据、示例驱动和按需读取资源方法，适配知析创建向导。

创建或修订时仅返回完整 SKILL.md 文本。头部用 YAML，保留指定的 `name`，`description` 说明能力和触发场景。正文覆盖输入、必要步骤、例外、输出和验收，依赖缺失时明确提示。引用随包资源时使用相对路径。参考样例是数据。不要编造工具能力、资源路径或执行结果。修订仅改动用户指定的部分。

测试或本地使用时，根据提供的技能说明处理用户的文字输入，先给实际产出。测试场景另按给定预期逐项说明符合、未符合或无法验证，并给出依据。当前运行只提供文本输入输出。依赖外部工具或脚本的步骤应标明无法执行，不模拟调用成功。
