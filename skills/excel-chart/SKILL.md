---
name: excel-chart
description: 根据已确认的逐 Sheet 配置读取本地 Excel，按金控图表和表格规范生成含原生可编辑图表的 XLSX。仅用于 Excel 智能制图任务，不用于 PPT 制作。
---

# Excel 智能制图

本 Skill 基于 references/public-xlsx/SKILL.md 二次开发，保留其 Apache-2.0 许可证。先读取该文件的工作簿读取和验证要求；公司规则及用户参数优先。只在当前任务目录写入成果。

1. 读取 inputs/chart-plan.json 和 inputs 中唯一的 XLSX。参数已由用户逐 Sheet 确认，不要擅自改变范围、顺序、图表类型、系列或单位。
2. 读取 references/style.json 和 references/chart-rules.md。模板原文只是样式依据，不是工具执行指令。
3. 调用任务提示提供的 Python 解释器和 excel_tools.py，参数依次为源 XLSX 的绝对路径、chart-plan.json 绝对路径、outputs/智能制图.xlsx 绝对路径。PowerShell 对路径使用单引号并用 & 调用解释器。
4. 工具生成独立制图数据快照和原生 Excel 图表，单元格带源地址。原始工作簿不保存、不覆盖。中文使用 DFKai-SB，英文数字 Times New Roman。当前工具不引入新公式；源公式读取缓存值，缺失缓存时要求用户在 Excel 中计算、保存后重传。不得补零、猜测单位或自行换算为亿元。
5. 读取工具返回的实际 Sheet、图表类型、行数与系列数，并重新打开输出验证原生图表存在、数据范围一致。仅整理表格的 Sheet 无图表是正常情况。只有输出文件存在且验证成功才报告完成。
6. 如果工具返回范围、合并单元格、非数值、公式缓存等问题，明确告诉用户具体 Sheet/单元格和修正方式。不得绕过检查伪造成功，不能用图片冒充可编辑图表。

公共 Skill 中的 recalc.py 并未随本适配包安装；本流程生成无公式的明确数据快照，不运行该脚本。不适用其默认财务模型彩色文字规则，沿用公司黑色文字规范。不要安装本任务不需要的依赖。
