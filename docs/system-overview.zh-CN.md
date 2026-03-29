# UNICC AI Safety Council — 系统说明（中文版）

英文版见同目录：[system-overview.en.md](./system-overview.en.md)

---

## 1. 系统是什么

UNICC AI Safety Council 是一套面向联合国与人道主义场景的 AI 安全评估流水线：对「待部署的 AI 系统」进行多维度分析，通过三位专家并行评估、六条定向交叉批评、规则仲裁，输出结构化结论（通过 / 需复核 / 不通过）及可追溯依据。

评估对象可以是聊天机器人、Agent、带工具或 MCP 的系统等。核心输入是一段系统描述文本，可由用户粘贴，或从 PDF、JSON、Markdown 文件解析得到。

---

## 2. 目标与产出

- Expert 1（安全与对抗）：技术风险、对抗鲁棒性、隐私与欺骗等；可选文档分析或完整主动攻击路径（见 Expert1 模块与独立 API）。
- Expert 2（治理与合规）：EU AI Act、GDPR、NIST、UNESCO 等；Agentic RAG 检索法规知识库后给出结论。
- Expert 3（UN 使命契合）：UN Charter、人道原则、UNESCO 伦理等；Agentic RAG 检索 UN 相关知识库。
- Council：六位专家两两方向的批评，再经规则仲裁得到 final_recommendation、共识程度、是否需人工监督等。

主要产出为 CouncilReport（JSON），包含 expert_reports、critiques、council_decision、council_note、incident_id 等。持久化包括：

- council/reports/{incident_id}.json
- council/council.db（SQLite，供列表与检索）
- council/knowledge_index.jsonl（摘要与原始 dict，便于后续向量检索扩展）

---

## 3. 架构概览

用户通过 real_frontend 访问；请求发往 frontend_api（默认端口 8100）。POST /evaluate/council 触发 CouncilOrchestrator：并行三位专家、并行六条批评、仲裁、council_decision，并调用 persist_report 写入 JSON、数据库与 JSONL。

GET /evaluations 与 GET /evaluations/{id} 用于历史与单条报告；另有 Markdown 下载端点。

可选：api 目录在端口 8000 提供仅 Expert 1 的 POST /evaluate/expert1-attack（Mode A/B），与完整 Council HTTP 流程独立。

模型后端可为 Claude API（开发演示）或 vLLM 加 Llama 3 70B（本地部署），由 council 与各 Expert 模块配置。

---

## 4. 仓库结构（Capstone 根目录）

- council/：编排、报告结构、批评、存储、SLM 后端封装等。
- Expert1/、Expert 2/、Expert 3/：各专家实现与数据。
- frontend_api/：面向前端的 FastAPI（Council、历史、Markdown 等），推荐使用。
- api/：Expert 1 独立 HTTP 服务。
- real_frontend/：生产 Web UI，默认请求 frontend_api 8100。
- mock_frontend/：静态演示 UI，不调后端；数据来自 mockData.ts。
- benchmark_data/ 等：基准与标注数据（若存在）。
- UNICC-Project-2/：可与本仓库并存的子项目；完整 monorepo 下生产前端在根的 real_frontend/。

---

## 5. 快速运行

### 5.1 完整 Council（Python）

在 Capstone 根目录设置 ANTHROPIC_API_KEY（或 vLLM 配置），调用 council.council_orchestrator.evaluate_agent，传入 agent_id、system_description、system_name、backend 等。

### 5.2 前端加 frontend_api（推荐体验）

终端一：pip install -r frontend_api/requirements.txt，然后 uvicorn frontend_api.main:app --reload --port 8100。

终端二：cd real_frontend，npm install，npm run dev。浏览器打开 Vite 提示的地址（通常为 http://localhost:5173）。New Evaluation 调用 POST /evaluate/council；Dashboard 使用 GET /evaluations。

### 5.3 仅 Expert 1 API

pip install -r api/requirements.txt，uvicorn api.main:app --reload --port 8000。Swagger：http://localhost:8000/docs。

### 5.4 静态演示前端

cd mock_frontend，npm install，npm run dev。无需 Python。说明见 mock_frontend/README.zh-CN.md。

---

## 6. HTTP API 摘要（frontend_api）

- GET /health：健康检查
- POST /evaluate/council：完整 Council 评估并持久化
- POST /evaluate/expert1-attack：仅 Expert 1
- GET /evaluations：历史列表（分页）
- GET /evaluations/{incident_id}：完整报告 JSON
- GET /evaluations/{incident_id}/markdown：报告 Markdown 附件
- GET /knowledge/index、GET /knowledge/search：知识索引与简单搜索

OpenAPI：http://localhost:8100/docs。

---

## 7. 核心数据契约（前端与集成方）

提交评估至少需要：agent_id、system_name、system_description（长文本）。可选 purpose、deployment_context、data_access、risk_indicators、backend（claude 或 vllm）等。

响应 JSON 与 council/test_output_refugeeassist.json 一类结构对齐（含 incident_id）。生产前端通过 real_frontend/src/utils/mapCouncilReport.ts 映射为界面模型；Final Report 支持浏览器端 Markdown 导出。

---

## 8. 配置与安全

API 密钥使用环境变量（如 ANTHROPIC_API_KEY），勿将 .env 提交到 Git。.gitignore 已忽略常见密钥文件与 node_modules 等。

---

## 9. 能力边界与后续方向

当前未包含：从 GitHub 或本地目录自动扫描生成系统描述（无独立仓库分析模块）；报告 PDF 导出（JSON 与 Markdown 已有，前端可导出 Markdown）；基于 knowledge_index.jsonl 的向量检索服务（数据已预留）。

可选路线图：PDF 导出、向量记忆、vLLM 微调、更细权限与审计日志等。

---

## 10. 文档索引

- 本文 system-overview.zh-CN.md：系统总览（中文）
- system-overview.en.md：同上（英文）
- 仓库根 README.md：英文概览（GitHub 默认展示）
- frontend_api/README.md：API 启动与示例
- mock_frontend/README.zh-CN.md：静态前端说明

文档版本随代码演进更新；以仓库内实现与 OpenAPI 为准。
