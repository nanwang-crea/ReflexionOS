# ReflexionOS 项目目录结构树

> 生成时间：2026-06-24
> 说明：已忽略 `node_modules`、`.git`、`dist`、`build`、`release`、`__pycache__` 等编译产物目录

---

## 概览

ReflexionOS 是一个 AI 编程助手桌面应用，采用 **Electron + React（前端）** + **Python FastAPI（后端）** 的架构。前端通过 Electron 桌面壳承载 Web UI，后端提供 LLM 对话、工具执行、记忆系统、技能/插件编排等核心能力。

---

```
ReflexionOS/
├── 📄 README.md                      # 项目总说明文档
├── 📄 CHANGELOG.md                   # 版本变更日志
├── 📄 BUG_REPORT.md                  # Bug 报告记录
├── 📄 problem.txt                    # 问题追踪/待解决问题
├── 📄 research_findings.md           # 调研成果记录
├── 📄 项目问题报告.md                  # 项目问题报告（中文）
├── 📄 start-dev.sh                   # 开发环境一键启动脚本（前后端）
├── 📄 start.sh                       # 生产环境启动脚本
│
├── 📂 backend/                       # 🐍 Python 后端（FastAPI）
│   ├── 📄 README.md                  # 后端说明文档
│   ├── 📄 pyproject.toml             # Python 项目元数据与依赖声明
│   ├── 📄 requirements.txt           # pip 依赖清单
│   ├── 📄 alembic.ini                # Alembic 数据库迁移配置
│   ├── 📄 conftest.py                # pytest 全局 fixture 配置
│   │
│   ├── 📂 app/                       # 🏗️ 后端应用主代码
│   │   ├── 📄 __init__.py            # 包初始化
│   │   ├── 📄 main.py                # FastAPI 应用入口，挂载路由与中间件
│   │   ├── 📄 app_services.py        # 应用级服务聚合/依赖注入容器
│   │   ├── 📄 errors.py              # 统一错误类型与异常定义
│   │   ├── 📄 ids.py                 # ID 生成与验证工具
│   │   ├── 📄 packaged_launcher.py   # 打包后（PyInstaller）的应用启动器
│   │   │
│   │   ├── 📂 agents/                # 🤖 子代理（Sub-Agent）系统
│   │   │   ├── 📄 __init__.py
│   │   │   └── 📄 sub_agent_runner.py # 子代理运行器，管理子代理生命周期与执行
│   │   │
│   │   ├── 📂 api/                   # 🌐 API 路由层
│   │   │   ├── 📄 __init__.py
│   │   │   ├── 📄 websocket_manager.py # WebSocket 连接管理器（实时通信）
│   │   │   └── 📂 routes/            # RESTful 路由定义
│   │   │       └── 📄 __init__.py
│   │   │
│   │   ├── 📂 browser/               # 🌍 内置浏览器管理
│   │   │   ├── 📄 __init__.py
│   │   │   ├── 📄 config.py          # 浏览器实例配置
│   │   │   ├── 📄 manager.py         # 浏览器生命周期管理器
│   │   │   └── 📄 models.py          # 浏览器相关数据模型
│   │   │
│   │   ├── 📂 config/                # ⚙️ 应用配置
│   │   │   ├── 📄 __init__.py
│   │   │   ├── 📄 settings.py        # 全局设置（环境变量、路径等）
│   │   │   └── 📄 logging_config.py  # 日志格式与级别配置
│   │   │
│   │   ├── 📂 execution/             # 🔄 核心执行引擎
│   │   │   ├── 📄 __init__.py
│   │   │   ├── 📄 rapid_loop.py      # 快速执行循环（主循环驱动器）
│   │   │   ├── 📄 approval_flow.py   # 工具调用审批流程
│   │   │   ├── 📄 approval_store.py  # 审批状态持久化
│   │   │   ├── 📄 context_compressor.py   # 上下文压缩器（长对话裁剪）
│   │   │   ├── 📄 context_manager.py     # 上下文管理器（组装 LLM 输入）
│   │   │   ├── 📄 conversation_history_loader.py # 对话历史加载器
│   │   │   ├── 📄 loop_message_builder.py # 循环消息构建器
│   │   │   ├── 📄 models.py          # 执行引擎数据模型
│   │   │   ├── 📄 plan_engine.py     # 计划引擎（多步骤任务规划）
│   │   │   ├── 📄 plan_file_sync.py  # 计划文件同步（持久化计划状态）
│   │   │   ├── 📄 prompt_manager.py  # Prompt 模板管理器
│   │   │   ├── 📄 runtime_tool_definitions.py # 运行时工具定义（注册可用工具）
│   │   │   ├── 📄 tool_registry.py   # 工具注册表
│   │   │   └── 📂 prompts/           # 📝 Prompt 模板文件
│   │   │       ├── 📄 system.txt              # 系统 prompt（默认）
│   │   │       ├── 📄 coding_appendix.txt     # 编码附录 prompt
│   │   │       ├── 📄 error.txt               # 错误处理 prompt
│   │   │       ├── 📄 final_response.txt      # 最终回复 prompt
│   │   │       ├── 📄 midrun_compress_input.txt   # 中途压缩-输入 prompt
│   │   │       ├── 📄 midrun_compress_system.txt  # 中途压缩-系统 prompt
│   │   │       ├── 📄 plan_mode.txt           # 计划模式 prompt
│   │   │       └── 📂 glm/                    # GLM 模型专用 prompt 变体
│   │   │           ├── 📄 system.txt
│   │   │           ├── 📄 coding_appendix.txt
│   │   │           ├── 📄 error.txt
│   │   │           ├── 📄 final_response.txt
│   │   │           ├── 📄 midrun_compress_input.txt
│   │   │           ├── 📄 midrun_compress_system.txt
│   │   │           └── 📄 plan_mode.txt
│   │   │
│   │   ├── 📂 llm/                   # 🧠 LLM 客户端层
│   │   │   ├── 📄 __init__.py
│   │   │   ├── 📄 base.py            # LLM 抽象基类
│   │   │   ├── 📄 openai_adapter.py  # OpenAI 兼容接口适配器
│   │   │   ├── 📄 client_headers.py  # HTTP 请求头构建
│   │   │   ├── 📄 dsml_tool_parser.py # DSML 工具调用格式解析器
│   │   │   ├── 📄 retry.py           # LLM 调用重试策略
│   │   │   └── 📄 token_counter.py   # Token 计数器
│   │   │
│   │   ├── 📂 memory/                # 🧩 记忆系统
│   │   │   ├── 📄 __init__.py
│   │   │   ├── 📄 working_memory.py  # 工作记忆（会话级上下文片段）
│   │   │   ├── 📄 memory_extractor.py # 记忆提取器（从对话中提取关键信息）
│   │   │   ├── 📄 recall_service.py  # 记忆召回服务（跨会话检索）
│   │   │   ├── 📄 session_tracker.py # 会话追踪器
│   │   │   ├── 📄 message_normalizer.py # 消息格式标准化
│   │   │   ├── 📄 payload_utils.py   # 载荷工具函数
│   │   │   └── 📄 text_compaction.py # 文本压缩/精简
│   │   │
│   │   ├── 📂 models/                # 📊 数据模型（Pydantic）
│   │   │   ├── 📄 __init__.py
│   │   │   ├── 📄 approval.py        # 审批相关模型
│   │   │   ├── 📄 conversation.py    # 对话模型
│   │   │   ├── 📄 conversation_snapshot.py # 对话快照模型
│   │   │   ├── 📄 file_content.py    # 文件内容模型
│   │   │   ├── 📄 file_tree.py       # 文件树模型
│   │   │   ├── 📄 git.py             # Git 相关模型
│   │   │   ├── 📄 llm_config.py      # LLM 配置模型
│   │   │   ├── 📄 message_search_document.py # 消息搜索文档模型
│   │   │   ├── 📄 project.py         # 项目模型
│   │   │   └── 📄 session.py         # 会话模型
│   │   │
│   │   ├── 📂 orchestration/         # 🎯 技能与插件编排层
│   │   │   ├── 📄 __init__.py
│   │   │   ├── 📄 skill_registry.py  # 技能注册表
│   │   │   ├── 📄 skill_parser.py    # 技能定义解析器
│   │   │   ├── 📄 skill_sorting.py   # 技能排序/优先级
│   │   │   ├── 📄 plugin_loader.py   # 插件加载器
│   │   │   ├── 📄 mcp_manager.py     # MCP（Model Context Protocol）管理器
│   │   │   └── 📄 package_resolver.py # 包依赖解析器
│   │   │
│   │   ├── 📂 services/              # 🔧 业务服务层
│   │   │   ├── 📄 __init__.py
│   │   │   ├── 📄 agent_service.py           # 代理服务（子代理调度）
│   │   │   ├── 📄 attachment_service.py      # 附件服务（文件/图片上传）
│   │   │   ├── 📄 cleanup_service.py         # 清理服务（过期数据清理）
│   │   │   ├── 📄 conversation_broadcaster.py # 对话广播器（WebSocket 推送）
│   │   │   ├── 📄 conversation_projection.py # 对话投影（视图层数据转换）
│   │   │   ├── 📄 conversation_runtime_adapter.py # 对话运行时适配器
│   │   │   ├── 📄 conversation_service.py    # 对话服务（CRUD + 业务逻辑）
│   │   │   ├── 📄 file_content_service.py    # 文件内容服务（读写项目文件）
│   │   │   ├── 📄 git_service.py             # Git 服务（状态查询、提交等）
│   │   │   ├── 📄 llm_provider_service.py    # LLM 提供商配置服务
│   │   │   ├── 📄 project_service.py         # 项目服务（项目管理）
│   │   │   └── 📄 session_service.py         # 会话服务（会话生命周期）
│   │   │
│   │   └── 📂 security/              # (推断) 安全与沙箱模块
│   │       └── ...
│   │
│   ├── 📂 alembic/                   # 🗃️ 数据库迁移
│   │   ├── 📄 env.py                 # 迁移环境配置
│   │   ├── 📄 script.py.mako         # 迁移脚本模板
│   │   └── 📂 versions/              # 迁移版本文件
│   │       ├── 📄 d3185a24f1c8_initial_schema.py          # 初始数据库 schema
│   │       ├── 📄 a1b2c3d4e5f6_add_agent_mode_to_sessions.py # 会话表增加代理模式字段
│   │       ├── 📄 b2c3d4e5f6a7_tool_trace_role_to_tool.py   # 工具追踪角色字段调整
│   │       └── 📄 c4d5e6f7a8b9_add_message_attachments.py   # 消息附件表
│   │
│   ├── 📂 storage/                   # 💾 本地存储
│   │   └── 📂 uploads/               # 用户上传文件存储目录
│   │
│   └── 📂 tests/                     # 🧪 后端测试套件（pytest）
│       ├── 📄 __init__.py
│       ├── 📄 test_app_services.py
│       ├── 📄 test_errors.py
│       ├── 📄 test_file_content_api.py
│       │
│       ├── 📂 test_api/              # API 路由测试
│       │   ├── 📄 __init__.py
│       │   ├── 📄 test_conversation_api.py
│       │   ├── 📄 test_conversation_websocket.py
│       │   ├── 📄 test_plugins_api.py
│       │   ├── 📄 test_sessions_api.py
│       │   ├── 📄 test_skills_api.py
│       │   └── 📄 test_upload.py
│       │
│       ├── 📂 test_browser/          # 浏览器模块测试
│       │   ├── 📄 __init__.py
│       │   ├── 📄 test_browser_integration.py
│       │   └── 📄 test_browser_manager.py
│       │
│       ├── 📂 test_conversation/     # 对话模块测试
│       │   └── 📄 test_edit_and_rerun.py
│       │
│       ├── 📂 test_execution/        # 执行引擎测试
│       │   ├── 📄 test_approval_store.py
│       │   ├── 📄 test_context_compressor.py
│       │   ├── 📄 test_context_manager.py
│       │   ├── 📄 test_conversation_history_loader.py
│       │   ├── 📄 test_loop_message_builder.py
│       │   ├── 📄 test_midrun_compaction.py
│       │   ├── 📄 test_multimodal_content.py
│       │   ├── 📄 test_multimodal_e2e.py
│       │   ├── 📄 test_plan_engine.py
│       │   ├── 📄 test_plan_file_sync.py
│       │   ├── 📄 test_prompt_manager.py
│       │   ├── 📄 test_rapid_loop.py
│       │   ├── 📄 test_runtime_tool_definitions.py
│       │   ├── 📄 test_session_tracker.py
│       │   ├── 📄 test_task_anchor_multimodal.py
│       │   ├── 📄 test_token_counter.py
│       │   ├── 📄 test_working_memory.py
│       │   └── 📄 test_working_memory_tool.py
│       │
│       ├── 📂 test_llm/              # LLM 客户端测试
│       │   ├── 📄 test_base.py
│       │   ├── 📄 test_dsml_tool_parser.py
│       │   ├── 📄 test_openai_adapter.py
│       │   └── 📄 test_retry.py
│       │
│       ├── 📂 test_memory/           # 记忆系统测试
│       │   ├── 📄 test_message_normalizer.py
│       │   └── 📄 test_recall_service.py
│       │
│       ├── 📂 test_models/           # 数据模型测试
│       │   └── 📄 test_project.py
│       │
│       ├── 📂 test_orchestration/    # 编排层测试
│       │   ├── 📄 __init__.py
│       │   ├── 📄 test_mcp_manager.py
│       │   ├── 📄 test_package_resolver.py
│       │   ├── 📄 test_plugin_loader.py
│       │   ├── 📄 test_skill_parser.py
│       │   └── 📄 test_skill_registry.py
│       │
│       ├── 📂 test_security/         # 安全模块测试
│       │   ├── 📄 __init__.py
│       │   ├── 📄 test_command_arity.py
│       │   ├── 📄 test_command_effect_registry.py
│       │   ├── 📄 test_command_effect_registry_network.py
│       │   ├── 📄 test_command_policy.py
│       │   ├── 📄 test_effect_category.py
│       │   ├── 📄 test_sandbox.py
│       │   ├── 📄 test_sandbox_error_detector.py
│       │   ├── 📄 test_session_trust_store.py
│       │   └── 📄 test_shell_tool_elevation.py
│       │
│       ├── 📂 test_services/         # 服务层测试
│       │   ├── 📄 test_agent_service.py
│       │   ├── 📄 test_attachment_service.py
│       │   ├── 📄 test_cleanup.py
│       │   ├── 📄 test_cleanup_service.py
│       │   ├── 📄 test_conversation_broadcaster.py
│       │   ├── 📄 test_conversation_projection.py
│       │   ├── 📄 test_conversation_runtime_adapter.py
│       │   ├── 📄 test_conversation_service.py
│       │   ├── 📄 test_llm_provider_service.py
│       │   └── 📄 test_session_service.py
│       │
│       ├── 📂 test_storage/          # 存储层测试
│       │   ├── 📄 __init__.py
│       │   ├── 📄 test_conversation_repositories.py
│       │   └── 📄 test_project_repository.py
│       │
│       └── 📂 test_tools/            # 工具测试
│           ├── 📄 test_browser_tool.py
│           ├── 📄 test_edit_tool.py
│           ├── 📄 test_file_tool.py
│           ├── 📄 test_glob_tool.py
│           ├── 📄 test_grep_tool.py
│           ├── 📄 test_patch_tool.py
│           ├── 📄 test_plan_tool.py
│           ├── 📄 test_registry.py
│           ├── 📄 test_session_recall_tool.py
│           ├── 📄 test_shell_tool.py
│           └── 📄 test_skill_tool.py
│
├── 📂 frontend/                      # ⚛️ 前端（Electron + React + TypeScript）
│   ├── 📄 package.json               # Node.js 依赖与脚本声明
│   ├── 📄 pnpm-lock.yaml             # pnpm 锁定文件
│   ├── 📄 tsconfig.json              # TypeScript 编译配置
│   ├── 📄 index.html                 # 入口 HTML 文件
│   ├── 📄 electron-builder.yml       # Electron 打包配置
│   ├── 📄 eslint.config.js           # ESLint 代码规范配置
│   ├── 📄 postcss.config.js          # PostCSS 配置
│   ├── 📄 tailwind.config.js         # Tailwind CSS 配置
│   ├── 📄 vite.config.ts             # Vite 构建工具配置
│   │
│   ├── 📂 electron/                  # 🖥️ Electron 主进程
│   │   ├── 📄 main.cjs               # Electron 主进程入口
│   │   ├── 📄 preload.cjs            # 预加载脚本（IPC 桥接）
│   │   ├── 📄 backend-manager.cjs    # 后端进程管理器（启动/停止 Python 后端）
│   │   └── 📄 backend-runtime-requirements.cjs # 后端运行时依赖检查
│   │
│   ├── 📂 scripts/                   # 📜 构建/开发脚本
│   │   └── (空)
│   │
│   ├── 📂 build-resources/           # 🎨 打包资源（图标等）
│   │   └── (空)
│   │
│   └── 📂 src/                       # 📦 前端源码
│       ├── 📄 main.tsx               # React 应用入口
│       ├── 📄 App.tsx                # 根组件（路由与布局）
│       ├── 📄 index.css              # 全局样式
│       ├── 📄 vite-env.d.ts          # Vite 类型声明
│       │
│       ├── 📂 components/            # 🧱 通用 UI 组件
│       │   ├── 📂 animations/        # 动画组件
│       │   │   └── 📄 SlideIn.tsx     # 滑入动画
│       │   │
│       │   ├── 📂 chat/              # 聊天组件
│       │   │   ├── 📄 ChatInput.tsx   # 聊天输入框（支持图片上传）
│       │   │   ├── 📄 ImagePreview.tsx # 图片预览
│       │   │   ├── 📄 MarkdownRenderer.tsx # Markdown 渲染器
│       │   │   └── 📂 __tests__/
│       │   │       └── 📄 ChatInput.test.ts
│       │   │
│       │   ├── 📂 common/            # 通用基础组件
│       │   │   └── 📄 Toast.tsx       # Toast 通知组件
│       │   │
│       │   ├── 📂 execution/         # 执行相关组件
│       │   │   ├── 📄 ActionReceipt.tsx    # 操作回执展示
│       │   │   ├── 📄 approvalActions.ts   # 审批操作逻辑
│       │   │   └── 📄 receiptUtils.ts      # 回执工具函数
│       │   │
│       │   ├── 📂 layout/            # 布局组件
│       │   │   ├── 📄 WorkspaceSidebar.tsx     # 工作区侧边栏
│       │   │   ├── 📄 SessionStatusBadge.tsx   # 会话状态徽章
│       │   │   ├── 📄 sidebarBusy.ts           # 侧边栏忙碌状态逻辑
│       │   │   ├── 📄 sidebarSessionState.ts   # 侧边栏会话状态
│       │   │   ├── 📄 useSidebarFilteredProjects.ts # 侧边栏项目过滤 hook
│       │   │   ├── 📄 useSidebarProjectActions.ts   # 侧边栏项目操作 hook
│       │   │   ├── 📄 useSidebarSessionActions.ts   # 侧边栏会话操作 hook
│       │   │   └── 📂 __tests__/
│       │   │       ├── 📄 sidebarBusy.test.ts
│       │   │       ├── 📄 sidebarSessionState.test.ts
│       │   │       ├── 📄 useSidebarFilteredProjects.test.ts
│       │   │       ├── 📄 useSidebarProjectActions.test.ts
│       │   │       └── 📄 useSidebarSessionActions.test.ts
│       │   │
│       │   ├── 📂 terminal/          # 终端组件
│       │   │   ├── 📄 TerminalInstance.tsx # 终端实例（xterm.js 封装）
│       │   │   ├── 📄 TerminalPanel.tsx   # 终端面板容器
│       │   │   └── 📄 TerminalTabBar.tsx  # 终端标签栏
│       │   │
│       │   └── 📂 workspace/         # 工作区核心组件（25 个文件）
│       │       ├── 📄 AssistantMessageItem.tsx  # AI 助手消息气泡
│       │       ├── 📄 UserMessageItem.tsx       # 用户消息气泡
│       │       ├── 📄 SystemNoticeItem.tsx      # 系统通知消息
│       │       ├── 📄 CodeEditor.tsx            # 代码编辑器（Monaco Editor）
│       │       ├── 📄 CodeTab.tsx               # 代码标签页
│       │       ├── 📄 CodeTabBar.tsx            # 代码标签栏
│       │       ├── 📄 EditableDiffViewer.tsx    # 可编辑 Diff 查看器
│       │       ├── 📄 FileSidebar.tsx           # 文件侧边栏
│       │       ├── 📄 FileTreeItem.tsx          # 文件树节点
│       │       ├── 📄 DelegateToolCall.tsx      # 委托工具调用展示
│       │       ├── 📄 MessageActions.tsx        # 消息操作按钮（复制、重试等）
│       │       ├── 📄 PlanProgress.tsx          # 计划进度展示
│       │       ├── 📄 ProcessGroupBlock.tsx     # 进程组块展示
│       │       ├── 📄 RunningIndicator.tsx      # 运行中指示器
│       │       ├── 📄 SubAgentDetailPanel.tsx   # 子代理详情面板
│       │       ├── 📄 ThinkingBlock.tsx         # 思考过程展示块
│       │       ├── 📄 ToolGroupItem.tsx         # 工具调用分组
│       │       ├── 📄 ToolTraceCard.tsx         # 工具追踪卡片
│       │       ├── 📄 WorkingNoteBlock.tsx      # 工作笔记块
│       │       ├── 📄 WorkspaceHeader.tsx       # 工作区头部栏
│       │       ├── 📄 WorkspaceTranscript.tsx   # 工作区对话流（主视图）
│       │       ├── 📄 runtimeStatus.ts          # 运行时状态逻辑
│       │       └── 📄 transcriptItems.ts        # 对话流项目构建器
│       │
│       ├── 📂 features/              # 🎯 功能模块（Feature-based 架构）
│       │   ├── 📂 code/              # 代码编辑功能
│       │   │   ├── 📂 api/
│       │   │   │   └── 📄 file.api.ts          # 文件 API 客户端
│       │   │   ├── 📂 stores/
│       │   │   │   └── 📄 codeTab.store.ts     # 代码标签页状态管理
│       │   │   └── 📂 __tests__/
│       │   │       └── 📄 codeTab.store.test.ts
│       │   │
│       │   ├── 📂 conversation/      # 对话功能
│       │   │   ├── 📄 conversation.reducer.ts # 对话状态 reducer
│       │   │   ├── 📂 api/
│       │   │   │   └── 📄 conversation.api.ts  # 对话 API 客户端
│       │   │   ├── 📂 hooks/
│       │   │   │   └── 📄 useImageUpload.ts    # 图片上传 hook
│       │   │   ├── 📂 stores/
│       │   │   │   └── 📄 conversation.store.ts # 对话状态管理
│       │   │   └── 📂 __tests__/
│       │   │       ├── 📄 conversation.api.test.ts
│       │   │       ├── 📄 conversation.reducer.test.ts
│       │   │       └── 📄 conversation.store.test.ts
│       │   │
│       │   ├── 📂 files/             # 文件管理功能
│       │   │   └── (空)
│       │   │
│       │   ├── 📂 git/               # Git 功能
│       │   │   ├── 📂 api/
│       │   │   │   └── 📄 git.api.ts           # Git API 客户端
│       │   │   └── 📂 stores/
│       │   │       └── 📄 git.store.ts         # Git 状态管理
│       │   │
│       │   ├── 📂 llm/               # LLM 配置功能
│       │   │   ├── 📄 llmSettings.loader.ts   # LLM 设置加载器
│       │   │   ├── 📄 provider.actions.ts     # 提供商操作
│       │   │   ├── 📄 providerDraft.ts        # 提供商配置草稿
│       │   │   ├── 📄 useSettingsPageController.ts # 设置页控制器 hook
│       │   │   ├── 📂 api/
│       │   │   │   └── 📄 llm.api.ts           # LLM API 客户端
│       │   │   └── 📂 __tests__/
│       │   │       └── 📄 llmSettings.loader.test.ts
│       │   │
│       │   ├── 📂 plugins/           # 插件功能
│       │   │   └── 📂 api/
│       │   │       └── 📄 plugin.api.ts        # 插件 API 客户端
│       │   │
│       │   ├── 📂 projects/          # 项目管理功能
│       │   │   ├── 📄 project.loader.ts       # 项目数据加载器
│       │   │   ├── 📂 api/
│       │   │   │   └── 📄 project.api.ts       # 项目 API 客户端
│       │   │   ├── 📂 stores/
│       │   │   │   └── 📄 project.store.ts     # 项目状态管理
│       │   │   └── 📂 __tests__/
│       │   │       └── 📄 project.loader.test.ts
│       │   │
│       │   ├── 📂 sessions/          # 会话管理功能
│       │   │   ├── 📄 session.actions.ts      # 会话操作（创建、切换等）
│       │   │   ├── 📂 api/
│       │   │   │   └── 📄 session.api.ts       # 会话 API 客户端
│       │   │   ├── 📂 hooks/
│       │   │   │   └── 📄 useSessionActions.ts # 会话操作 hook
│       │   │   ├── 📂 stores/
│       │   │   │   └── 📄 session.store.ts     # 会话状态管理
│       │   │   └── 📂 __tests__/
│       │   │       ├── 📄 session.actions.test.ts
│       │   │       └── 📄 session.store.test.ts
│       │   │
│       │   ├── 📂 settings/          # 设置功能
│       │   │   ├── 📂 api/
│       │   │   │   └── 📄 uiSettings.api.ts    # UI 设置 API
│       │   │   └── 📂 stores/
│       │   │       └── 📄 settings.store.ts    # 设置状态管理
│       │   │
│       │   ├── 📂 skills/            # 技能功能
│       │   │   ├── 📂 api/
│       │   │   │   └── 📄 skill.api.ts         # 技能 API 客户端
│       │   │   ├── 📂 components/
│       │   │   │   ├── 📄 LoadMoreButton.tsx   # 加载更多按钮
│       │   │   │   └── 📄 PluginFilter.tsx     # 插件过滤器
│       │   │   ├── 📂 hooks/
│       │   │   │   └── 📄 useSkillList.ts      # 技能列表 hook
│       │   │   └── 📂 utils/
│       │   │       └── 📄 skillHelpers.ts      # 技能辅助函数
│       │   │
│       │   ├── 📂 terminal/          # 终端功能
│       │   │   ├── 📂 stores/
│       │   │   │   └── 📄 terminal.store.ts    # 终端状态管理
│       │   │   └── 📂 __tests__/
│       │   │       └── 📄 terminal.store.test.ts
│       │   │
│       │   └── 📂 workspace/         # 工作区功能
│       │       ├── 📄 autoScroll.ts           # 自动滚动逻辑
│       │       ├── 📄 sessionSelection.ts     # 会话选择逻辑
│       │       ├── 📄 types.ts               # 工作区类型定义
│       │       ├── 📂 stores/
│       │       │   ├── 📄 workspace.store.ts  # 工作区状态管理
│       │       │   └── 📂 __tests__/
│       │       │       └── 📄 workspace.store.test.ts
│       │       └── 📂 __tests__/
│       │           ├── 📄 autoScroll.test.ts
│       │           └── 📄 sessionSelection.test.ts
│       │
│       ├── 📂 hooks/                 # 🪝 全局 React Hooks
│       │   ├── 📄 useConversationData.ts      # 对话数据 hook
│       │   ├── 📄 useConversationRuntime.ts   # 对话运行时 hook
│       │   ├── 📄 useCurrentSessionViewModel.ts # 当前会话视图模型
│       │   ├── 📄 useSendMessage.ts           # 发送消息 hook
│       │   ├── 📄 useSessionData.ts           # 会话数据 hook
│       │   ├── 📄 useSessionSelection.ts      # 会话选择 hook
│       │   ├── 📄 useSessionUnreadState.ts    # 会话未读状态 hook
│       │   ├── 📄 useStreamingMessage.ts      # 流式消息 hook
│       │   ├── 📄 useSubAgentEvents.ts        # 子代理事件 hook
│       │   ├── 📄 useToast.ts                 # Toast 通知 hook
│       │   └── 📂 __tests__/
│       │       ├── 📄 useConversationData.test.ts
│       │       ├── 📄 useConversationRuntime.test.ts
│       │       ├── 📄 useConversationRuntime.multi-session.test.ts
│       │       ├── 📄 useCurrentSessionViewModel.test.ts
│       │       ├── 📄 useSendMessage.test.ts
│       │       ├── 📄 useSessionData.test.ts
│       │       └── 📄 useSessionSelection.test.ts
│       │
│       ├── 📂 pages/                 # 📄 页面级组件
│       │   ├── 📄 AgentWorkspace.tsx          # Agent 工作区页面（主页面）
│       │   ├── 📄 AutomationPage.tsx          # 自动化页面
│       │   ├── 📄 PluginsPage.tsx             # 插件管理页面
│       │   ├── 📄 SettingsPage.tsx            # 设置页面
│       │   ├── 📄 SkillsPage.tsx              # 技能管理页面
│       │   ├── 📂 settings/                   # 设置子页面
│       │   │   ├── 📄 AboutPanel.tsx          # 关于面板
│       │   │   ├── 📄 BrowserPanel.tsx        # 浏览器设置面板
│       │   │   ├── 📄 DefaultModelPanel.tsx   # 默认模型设置面板
│       │   │   ├── 📄 DisplayOptionsPanel.tsx # 显示选项面板
│       │   │   └── 📄 ProviderPanel.tsx       # LLM 提供商设置面板
│       │   └── 📂 __tests__/
│       │       └── 📄 AgentWorkspace.test.tsx
│       │
│       ├── 📂 services/              # 🔌 前端服务层
│       │   ├── 📄 apiClient.ts                # HTTP API 客户端（axios 封装）
│       │   ├── 📄 desktopClient.ts            # 桌面端 IPC 客户端
│       │   ├── 📄 dialogService.ts            # 对话框服务（文件选择等）
│       │   ├── 📄 runtimeConfig.ts            # 运行时配置
│       │   ├── 📄 sessionConversationWebSocket.ts # 会话 WebSocket 客户端
│       │   └── 📄 terminalIpc.ts              # 终端 IPC 通信
│       │
│       ├── 📂 shared/                # 🤝 共享模块
│       │   └── 📂 stores/            # 全局共享状态
│       │       ├── 📄 animation.store.ts      # 动画状态管理
│       │       ├── 📄 theme.store.ts          # 主题状态管理（暗色/亮色）
│       │       └── 📄 toast.store.ts          # Toast 通知状态管理
│       │
│       ├── 📂 types/                 # 📐 TypeScript 类型定义
│       │   ├── 📄 animation.ts               # 动画类型
│       │   ├── 📄 conversation.ts             # 对话类型
│       │   ├── 📄 electron.d.ts              # Electron API 类型声明
│       │   ├── 📄 file.ts                    # 文件类型
│       │   ├── 📄 fileTree.ts                # 文件树类型
│       │   ├── 📄 git.ts                     # Git 类型
│       │   ├── 📄 llm.ts                     # LLM 类型
│       │   ├── 📄 plan.ts                    # 计划类型
│       │   ├── 📄 plugin.ts                  # 插件类型
│       │   ├── 📄 project.ts                 # 项目类型
│       │   ├── 📄 skill.ts                   # 技能类型
│       │   └── 📄 workspace.ts               # 工作区类型
│       │
│       ├── 📂 utils/                 # 🔨 前端工具函数
│       │   ├── 📄 activeRun.ts               # 活跃运行状态工具
│       │   ├── 📄 llmHelpers.ts              # LLM 辅助函数
│       │   └── 📄 sessionActivity.ts         # 会话活跃度工具
│       │
│       └── 📂 constants/             # 📌 常量定义
│           └── 📄 visionModels.ts            # 视觉模型常量
│
├── 📂 docs/                          # 📚 项目文档
│   ├── 📄 README.md                  # 文档索引
│   ├── 📄 PROJECT_STATUS.md          # 项目状态概览
│   ├── 📄 next.txt                   # 下一步待办事项
│   ├── 📄 multimodal-integration-complete.md # 多模态集成完成报告
│   │
│   ├── 📂 devlog/                    # 📝 开发日志
│   │   ├── 📄 README.md              # 开发日志索引
│   │   └── 📄 devlog-2026-06-23_to_present.md # 开发日志（2026-06-23 至今）
│   │
│   └── 📂 superpowers/              # 🦸 Superpowers（设计文档与计划）
│       ├── 📄 README.md              # Superpowers 索引
│       ├── 📄 INSTALL.md             # 安装指南
│       │
│       ├── 📂 plans/                 # 实施计划
│       │   ├── 📄 2026-06-16-context-compressor-refactor.md
│       │   ├── 📄 2026-06-21-context-assembly-merge.md
│       │   ├── 📄 2026-06-22-multi-session-parallel-implementation-plan.md
│       │   ├── 📄 2026-06-22-working-note-final-response-bug-analysis.md
│       │   ├── 📄 2026-06-23-sub-agent-implementation.md
│       │   └── 📄 2026-06-23-working-memory-redesign.md
│       │
│       └── 📂 specs/                 # 设计规格文档
│           ├── 📄 2026-06-15-model-capabilities-config-driven-design.md
│           ├── 📄 2026-06-15-multimodal-frontend-design.md
│           ├── 📄 2026-06-16-context-compressor-refactor-design.md
│           ├── 📄 2026-06-21-working-memory-design.md
│           ├── 📄 2026-06-22-file-attachments-requirements.md
│           ├── 📄 2026-06-22-multi-session-parallel-requirements.md
│           ├── 📄 2026-06-22-working-memory-implementation-plan.md
│           └── 📄 2026-06-23-sub-agent-revised-design.md
│
├── 📂 packaging/                     # 📦 打包与分发
│   └── 📂 pyinstaller/               # PyInstaller 打包配置
│       └── 📄 reflexion-backend.spec # PyInstaller 打包规格文件
│
├── 📂 test_screenshots/              # 📸 测试截图目录（E2E 测试截图存储）
│   └── (空)
│
└── 📂 tests/                         # 🧪 集成/E2E 测试（顶层）
    └── (空)
```

---

## 架构分层说明

### 后端（Python / FastAPI）

| 层级 | 目录 | 职责 |
|------|------|------|
| **入口层** | `app/main.py` | FastAPI 应用初始化、中间件注册 |
| **路由层** | `app/api/routes/` | RESTful API 端点定义 |
| **服务层** | `app/services/` | 业务逻辑编排（对话、会话、Git、项目等） |
| **执行引擎** | `app/execution/` | AI 代理核心循环：prompt 管理、上下文压缩、工具调用、审批流程、计划引擎 |
| **LLM 层** | `app/llm/` | 大模型客户端抽象与适配（OpenAI 兼容接口） |
| **记忆系统** | `app/memory/` | 工作记忆、记忆提取、跨会话召回 |
| **编排层** | `app/orchestration/` | 技能注册、插件加载、MCP 协议管理 |
| **子代理** | `app/agents/` | 子代理运行与调度 |
| **浏览器** | `app/browser/` | 内置浏览器实例管理 |
| **模型层** | `app/models/` | Pydantic 数据模型定义 |
| **配置层** | `app/config/` | 全局配置与日志 |

### 前端（Electron / React / TypeScript）

| 层级 | 目录 | 职责 |
|------|------|------|
| **Electron 主进程** | `electron/` | 桌面窗口管理、后端进程管理、IPC 桥接 |
| **页面** | `src/pages/` | 顶层页面组件（工作区、设置、技能、插件） |
| **组件** | `src/components/` | UI 组件（聊天、终端、布局、工作区视图） |
| **功能模块** | `src/features/` | Feature-based 架构，每个功能含 api/stores/hooks |
| **Hooks** | `src/hooks/` | 全局可复用 React Hooks |
| **服务** | `src/services/` | HTTP/WebSocket/IPC 客户端 |
| **状态管理** | `src/shared/stores/` | 全局共享状态（主题、Toast、动画） |
| **类型** | `src/types/` | TypeScript 类型定义 |
| **工具** | `src/utils/` | 前端工具函数 |

### 技术栈总结

- **前端**：React 18 + TypeScript + Vite + Tailwind CSS + Electron + Zustand（状态管理）
- **后端**：Python 3 + FastAPI + SQLAlchemy + Alembic + Pydantic
- **通信**：RESTful API + WebSocket（实时流式对话）
- **AI**：OpenAI 兼容接口 + 自定义 Prompt 模板 + 工具调用（Function Calling）
- **打包**：Electron Builder（前端）+ PyInstaller（后端）
