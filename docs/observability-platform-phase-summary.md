# Observability Platform 阶段总结

更新时间：2026-07-27

> **⚠️ 状态更正（2026-09-01 核实）**
>
> **本文档描述的是设计目标，不是已交付代码。经核实，仓库中不存在任何监控平台实现。**
>
> 核实方式与结果：
> - `backend/app/` 下无 `monitoring/` 目录
> - 全仓库检索 `api/monitoring`、`logical_call`、`provider_request`、`model_pricing` 均零命中
> - `backend/app/main.py` 的 11 处 `include_router` 中无 monitoring 路由
> - `git log --all` 检索不到相关文件的任何历史记录
>
> 因此下文所有「状态：已完成」应理解为「设计已定稿，实现未开始」；
> 第 4 节「可以作为 v1 交付」的结论不成立。
> 若要推进此平台，起点是 Phase 1 的实现，而非第 5 节列出的增强项。

## 1. 能力清单（设计目标）

监控平台的设计目标可以按采集、可靠性、计费、查询和前端五层来理解。以下条目均为**规划中的**能力。

### 1.1 采集层

- LLM 逻辑调用采集：`logical_call`
- Provider 真实请求 attempt 采集：`provider_request`
- 工具调用采集：`tool_call`
- 审批事件采集：`approval`
- 删除/匿名化约束事件：`privacy_tombstone`

### 1.2 可靠性层

- SQLite 作为主事件存储
- fallback journal 本地持久化兜底
- memory fallback 作为最后降级路径
- `/api/monitoring/health` 健康状态输出
- 启动时 hanging 记录修复
- 删除后 tombstone 持续约束晚到事件

### 1.3 计费层

- `model_pricing` 价格记录
- exact / pattern / priority 匹配规则
- pricing snapshot 落库
- input / output / cached 分项成本计算
- `cost_status`：
  - `exact`
  - `estimated`
  - `incomplete`
  - `unpriced`

### 1.4 查询层

当前已提供以下监控接口：

- `GET /api/monitoring/health`
- `GET /api/monitoring/overview`
- `GET /api/monitoring/anomalies`
- `GET /api/monitoring/trends`
- `GET /api/monitoring/llm/requests`
- `GET /api/monitoring/llm/requests/{request_id}`
- `GET /api/monitoring/tools/calls`
- `GET /api/monitoring/tools/calls/{tool_call_metric_id}`
- `GET /api/monitoring/alerts`
- `PUT /api/monitoring/alerts`

### 1.5 前端层

当前前端已经有独立“监控中心”页面，并具备以下能力：

- 项目筛选
- 时间窗口筛选
- LLM 请求筛选
- 工具调用筛选
- 趋势图
- anomaly 视图
- request / tool 详情 drill-down
- URL 参数同步
- 告警阈值设置页
- 全局 toast 告警提醒
- 侧边栏监控告警徽标

## 2. 剩余增强项

以下内容不阻塞当前第一版使用，但属于下一阶段最值得继续推进的能力。

### 2.1 外部通知

- Webhook
- Slack / 飞书 / 企业微信通知
- 按 severity 分级通知

### 2.2 告警治理

- 告警历史
- 告警确认 / 静默
- 去重窗口
- 恢复通知

### 2.3 配置细化

- 项目级阈值
- 模型级阈值
- 工具级阈值
- 多窗口独立阈值

### 2.4 页面增强

- 保存视图
- 常用预设筛选
- 更细粒度图表
- 运行时间线视图
- 从 detail 跳转到 run / session / project

### 2.5 数据治理与运维

- journal 清理策略再细化
- shadow rebuild / 高水位切换工具化
- observability 自监控面板

## 3. 阶段总结 / 里程碑清单

建议把当前监控平台建设拆成以下阶段来定义。

### Phase 1：监控底座

- 事件模型
- 投影表
- 隐私删除
- collector
- fallback journal
- health

状态：已完成

### Phase 2：LLM 与费用可观测

- provider attempt 级采集
- usage
- pricing matcher
- 成本计算
- trends / detail

状态：已完成

### Phase 3：工具与审批可观测

- tool metrics
- approval events
- denied / waiting / failed 口径
- anomaly 视图

状态：已完成

### Phase 4：监控中心可用版

- overview
- 列表
- detail
- URL 状态同步
- 告警阈值配置
- 应用内主动提醒

状态：已完成

### Phase 5：平台增强版

- 外部通知
- 保存视图
- 告警治理
- 更细粒度阈值

状态：未完成

## 4. 当前阶段结论

从产品和工程角度看，当前监控平台已经达到以下状态：

- 可以作为内部第一版监控中心投入使用
- 已经覆盖采集、费用、工具、审批、趋势、详情、异常、阈值和应用内提醒
- 剩余工作主要是平台增强项，而不是第一版阻塞项

简化结论：

- 作为 v1：已经可以交付
- 作为长期演进的平台：仍建议继续做 v1.5 / v2 增强

## 5. 建议的下一步

如果继续推进，优先级建议如下：

1. 外部通知能力
2. 告警治理
3. 保存视图 / 预设筛选
4. 更细图表与时间线视图

如果当前目标是先收口阶段成果，则建议把本文件作为当前监控平台的阶段性交付说明。
