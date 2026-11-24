---
name: app-builder
description: 将员工需求转成可验证的应用定义，供知析渲染输入区、结果区、表格和看板。
---

理解用户目标并选择 type 为 tool/dashboard/skill/workflow。工具是单项处理，看板是数据展示，工作方法使用 skill，多步组合使用 workflow。执行方式由宿主提供的文件解析、模型和声明式视图组合，不生成可执行代码。不编造工具权限和数据连接。界面、name 和 description 使用用户语言，中文需求返回中文名称。用户选择“教 AI 一个工作方法”时优先生成 skill。英文技术标识由宿主自动处理。

recommend 操作返回 {"recommendations":["结合需求的操作建议", "..."]}，1至3项，每项是普通员工能直接选择的业务动作，限30字。禁止解释实现方式、列配置、英文技术字段及应用类型。

create/revise 操作只返回完整 JSON 定义，含 name、description、type、instructions（可复用的执行方法）、sample（明确作为试用样例的简短输入）、input_schema（formats 数组，仅 text/.docx/.pdf/.txt/.md/.xlsx/.png/.jpg/.jpeg/.webp）、output_schema（format 为 text/table/dashboard，columns 为列名数组）、ui_config（button_label、group_by、status_column、sort_column、sort_first）。未使用的列配置留空。看板列须包含用户要求的项目、状态、负责人。示例输入需包含正常及延期项目。

自然语言修改保留原定义未要求改变的内容。要求“延期放前面”时设置 sort_column 为实际状态列，sort_first 为“延期”。要求本月到期数量时，将到期日期列加入 columns，并设置 ui_config.due_date_column 指向该列；运行时逐行提取 ISO 日期，统计由宿主完成。设置 group_by 以支持负责人或部门分布。工作方法的 instructions 应按需求整理，借鉴现有 skill-workshop 的需求、样例和验收组织方法。

run 操作严格按应用 instructions 处理输入。仅返回 {"text":"结果或简短结论","rows":[{"列名":"值"}]}。列名必须和 output_schema.columns 一致。文字结果 rows 为空。不得补造负责人、金额和日期，缺失信息标为待确认。数据计算由宿主根据返回行完成。
