# 液压支架总体设计 Agent

采煤工作面液压支架总体设计系统。B/S 架构，支持**传统软件模式**与 **Agent 对话模式**双交互。
架构详见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 进度: M1~M5 主体完成 ✅

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M1 | 数据模型 / 项目库 / 传统模式框架 | ✅ |
| M2 | 六大计算模块内核 (四连杆优化、运动仿真、受力分析、三大校核) | ✅ |
| M3 | 知识层 (GB 25974 / MT/T 587 条款结构化、材料库、案例库) | ✅ |
| M4 | LLM 适配器 (可插拔) + 智能体编排 + Agent 对话界面 | ✅ |
| M5 | 报告生成 / 双模式状态同步 / 轨迹可视化 | ✅ |

## 功能亮点

- **传统模式**: 模块树按 ①连杆优化→②运动仿真→③受力分析→④⑤⑥校核 主线组织，
  表单按模块字段声明自动渲染，运行前自动快照，支持任意版本回溯。
- **Agent 模式**: 自然语言描述需求（如"设计采高 2.4~5m、工作阻力 12000kN 的两柱掩护式支架"），
  智能体自动规划→补参→跑模块→判读→反思重试（≤3 次）→汇报。右侧状态面板实时同步。
- **计算内核**: 四连杆双纽线优化（定向随机搜索+多重启 Nelder-Mead，典型工况宽度 ~21mm）、
  整架 2D 静力平衡多工况求解、按 GB 25974 限值的强度/稳定性校核。
- **LLM 可插拔**: Anthropic 官方 SDK（默认 claude-opus-4-8）或任意 OpenAI 兼容端点
  （DeepSeek/Qwen/GLM…），用户在设置页自带 API Key，运行时可切换。
- **载荷传递零 LLM**: 受力分析结果由框架代码写入数据模型并分发给校核模块，
  数值链路全程确定性、可审计。

## 本地开发

```bash
# 后端 (默认 SQLite, 无需数据库)
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload          # http://localhost:8000/docs

# 前端
cd frontend
npm install
npm run dev                                       # http://localhost:5173

# 测试 (20 项)
cd backend && .venv/bin/python -m pytest tests/ -v
```

首次使用 Agent 模式: 顶栏「⚙ LLM 设置」→ 选服务商 → 填 API Key。

## Docker 部署

```bash
docker compose up -d --build    # 前端 http://localhost , 后端 http://localhost:8000
```

生产环境使用 PostgreSQL（pgvector 镜像，为知识层 RAG 扩展预留）。

## 目录结构

```
backend/
  app/
    models/support_model.py    # 统一参数化数据模型 (数据总线, 含脏标记传播)
    models/db_models.py        # ORM: Project/Design/Snapshot
    models/knowledge_models.py # ORM: 标准条款/材料/案例
    knowledge/seed.py          # 知识层种子数据 (示例值, 正式使用前须核对)
    modules/base.py            # 计算模块统一协议 + 注册表
    modules/fourbar.py         # 四连杆运动学求解与双纽线优化
    modules/impl.py            # 六大计算模块实现
    llm/base.py                # LLM 适配器统一接口
    llm/anthropic_adapter.py   # Anthropic 官方 SDK 适配器
    llm/openai_compat_adapter.py # OpenAI 兼容适配器
    llm/settings.py            # LLM 设置存储与工厂
    agent/orchestrator.py      # 智能体编排 (工具集+调用循环)
    agent/conversation.py      # 对话历史持久化
    api/routes.py              # REST API (项目/方案/参数/快照/模块/知识/报告)
    api/agent_routes.py        # Agent API (设置/对话 WS+REST)
    report.py                  # 计算报告生成 (Markdown/HTML)
  tests/                       # test_m1 / test_m2_m3 / test_m4
frontend/
  src/
    App.vue                    # 双模式布局 + 项目/方案管理
    components/ModuleTree.vue  # 模块树 (参数完整性/脏状态)
    components/ParamForm.vue   # 参数表单 (按模块字段自动渲染)
    components/ResultView.vue  # 结果视图 (含双纽线轨迹 SVG)
    components/AgentPanel.vue  # Agent 对话流 (WebSocket)
    components/SettingsDialog.vue # LLM 设置
docker-compose.yml
```

## 工程说明

- 计算模块采用**总体设计阶段简化力学模型**（平面 2D、静力平衡、材料力学公式），
  详细设计阶段应以有限元复核。
- 知识层标准条款限值为**工程常用示例值**，正式使用前须由工程师按现行标准原文逐条核对。
- API Key 明文存于服务端数据库（20 人内部测试可接受），生产环境应改为加密存储。
