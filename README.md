# 知析

面向金融分析师的 AI 办公、研究、阅读与应用共创工作台。此仓库供源码审阅。

入口为 server.py、worker.py 和 web/app.js。AI 工坊见 workshop_chat.py、planning_engine.py 与 integrations/workshop-ui。机构研究见 institution_research.py。

公开快照省略本地配置、密钥、业务数据、公司模板、标识、私有集成工程、第三方运行时和构建产物。完整业务运行需另行配置依赖及数据。

阅读助手支持导入公开公众号文章及合集。合集导入先列出可选文章，再提取所选正文；遇到微信验证时可粘贴正文，并保留原文链接。阅读工作区需要独立配置 ThinkFlow 与 Marginalia 集成，调用 ThinkFlow 上传接口时使用环境变量 `THINKFLOW_API_KEY`。
