# 后期可扩展性与中间件质量审查报告

**审查日期**: 2026-04-06
**项目**: LLM Evaluation Service
**定位**: 评估平台的 evaluation service，被上层调度层（orchestrator）调用的中间件服务

---

## 1. 总体评价

**评分**: 8.0/10

该服务在核心可扩展性方面设计良好，注册表架构、三层分离、动态路由生成等设计都降低了新增指标的成本。在中间件成熟度方面，错误码体系、API 设计质量表现不错。测试覆盖和可观测性方面有提升空间。认证、限流、幂等性、容器化部署由 infra 层（Terraform）统一管理，不纳入本次审查范围。

---

## 2. 可扩展性评估

### 2.1 新增 Metric 成本分析

**当前流程**: 对照 README "添加新指标" 验证，实际步骤与文档一致。

| 步骤 | 操作 | 涉及文件 | 复杂度 |
|------|------|----------|--------|
| 1 | 创建 metric 类文件 | `app/evaluators/{type}/{Metric}.py` | 低 |
| 2 | 定义 Request Model | 同上（Pydantic） | 低 |
| 3 | 实现 evaluate 方法 | 同上 | 中 |
| 4 | 注册到子注册表 | `app/evaluators/{type}/__init__.py` | 低 |
| 5 | 重启服务 | - | 低 |

**涉及文件数**: 3 个（metric 文件、子包 init、可能需要 prompt.yaml）

**优点**:
- 无需修改任何路由代码，动态注册机制自动生成单指标端点
- Duck-typing 验证避免基类继承，降低耦合
- request_model 与 metric 同文件，易于维护
- 支持可选字段 `optional_fields`，灵活性高

**改进空间**:
- prompt.yaml 与代码分离，修改 metric prompt 需要跨文件编辑
- 缺少 metric 版本管理机制（如 prompt 版本迭代）

### 2.2 新增 Evaluator Type 成本分析

**当前流程**:

| 步骤 | 操作 | 涉及文件 | 复杂度 |
|------|------|----------|--------|
| 1 | 创建子包目录 | `app/evaluators/{new_type}/` | 低 |
| 2 | 创建子注册表 | `registry.py` | 低 |
| 3 | 创建 metric 类 | `*.py` | 中 |
| 4 | 注册到子注册表 | `__init__.py` | 低 |
| 5 | 注册到顶层注册表 | `app/evaluators/__init__.py` | 低 |

**优点**:
- performance 目录已预留，架构支持非 LLM 类型（formula-based metrics）
- 子注册表模式统一，易于复制

**改进空间**:
- 缺少 evaluator type 的自动发现机制，需要手动 import
- 不同 evaluator type 共享相同的 LLM 调用基础设施，非 LLM 类型需要额外处理

### 2.3 配置扩展性

**现状**:
- 使用 pydantic-settings，支持 `.env` 文件
- 分三类配置：`DBSettings`、`LLMSettings`、`AppSettings`
- 支持请求级 LLM 配置覆盖（`model`, `temperature`）

**优点**:
- `extra="ignore"` 配置允许向后兼容添加新字段
- 请求级配置覆盖通过 ContextVar 实现，无侵入性

**不足**:
- 缺少配置热更新机制
- 缺少多环境配置管理（dev/staging/prod）
- retry 配置（`LLM_MAX_ATTEMPTS`, `LLM_BASE_WAIT` 等）是全局的，无法按 metric 调优
- 缺少 feature flag 机制

### 2.4 数据库扩展性

**表设计**:
- `evaluation_result`: 核心评估结果
- `llm_metadata`: LLM 调用详情，1:N 关联

**优点**:
- JSON 字段（`reason`, `messages`, `raw_response`）支持 metric 的差异化数据
- `task_id` 支持批量查询
- 支持 local/azure 双后端

**不足**:
- 缺少索引：`task_id` 有索引但 `metric_type` + `evaluated_at` 组合查询无索引，历史查询性能堪忧
- 缺少软删除机制
- 缺少评估结果版本追踪（如 metric 更新后的历史对比）
- JSON 字段难以进行结构化查询和聚合分析
- 无数据归档策略

---

## 3. 中间件质量评估

### 3.1 API 设计质量

**优点**:
- 单指标端点 Swagger 友好，每个 metric 有独立路由
- Batch 端点支持并发评估，降低 orchestrator 调用次数
- 使用 UUID 作为 `eval_id`，避免冲突
- 请求/响应模型分离（`request.py`/`response.py`），结构清晰

**不足**:
- 缺少 API 版本策略（目前只有 `/api/v1/`，但无版本兼容机制）
- 缺少分页机制（虽然当前不需要，但设计上未预留）
- Batch 端点无并发数限制，可能导致资源耗尽
- 缺少异步回调机制（长时间评估任务需要轮询）

### 3.2 错误码体系

**现状**:
```python
# 已定义错误码
LLM_AUTH_ERROR      # 500
LLM_RATE_LIMIT      # 503
LLM_TIMEOUT         # 504
LLM_BAD_REQUEST     # 500
METRIC_ERROR        # 500
UNKNOWN_METRIC      # 422
VALIDATION_ERROR    # 422
INTERNAL_ERROR      # 500
```

**优点**:
- 错误类型与 HTTP 状态码映射合理
- 错误响应结构统一（`error`, `message`, `eval_id`, `detail`）

**不足**:
- 缺少应用级错误码枚举（如 `EVAL_0001`），仅依赖字符串
- 错误码文档不完整，README 中的错误码表未覆盖所有场景
- `LLM_BAD_REQUEST` 返回 500 不合理，应该是 400
- 缺少错误码到国际化消息的映射

### 3.3 幂等性

> 由 infra 层统一管理（API Gateway / Terraform），不纳入应用层审查范围。

### 3.4 认证与安全

> 由 infra 层统一管理（API Gateway / Terraform），不纳入应用层审查范围。

### 3.5 限流与保护

> 由 infra 层统一管理（API Gateway / Terraform），不纳入应用层审查范围。

### 3.6 可观测性

**日志**:
- 基础 logging 配置存在，级别可配置
- 部分关键路径有日志（如 LLM retry）

**缺失**:
- 无结构化日志（JSON 格式）
- 无 trace ID 传递（无法追踪跨服务请求）
- 无 metrics 收集（Prometheus / StatsD）
- 无分布式追踪（OpenTelemetry）
- `/health` 端点过于简单，无依赖检查（DB、LLM 连通性）

---

## 4. 测试覆盖

**现状**:
- 仅 `tests/integration/test_evaluate_api.py` 一个测试文件
- 测试内容：
  - Health 检查
  - Faithfulness 成功场景
  - 验证错误（422）
  - LLM 错误路径（RateLimit, Timeout）
  - 自动生成 eval_id

**覆盖不足**:
- ❌ 无单元测试（registry、metric 逻辑）
- ❌ 无数据库层测试
- ❌ 无 Batch 端点测试
- ❌ 无并发场景测试
- ❌ 无配置验证测试
- ❌ 无 LLM retry 逻辑测试
- ❌ 无 persistence 异常处理测试
- ❌ 无性能测试

**测试覆盖估算**: < 20%

---

## 5. 部署就绪度

**现状**:

| 检查项 | 状态 | 说明 |
|--------|------|------|
| Dockerfile | ❌ 缺失 | 无容器化配置 |
| docker-compose | ❌ 缺失 | 无本地开发环境编排 |
| CI/CD 配置 | ❌ 缺失 | 无 GitHub Actions / GitLab CI |
| 健康检查 | ⚠️ 基础 | `/health` 端点存在但无深度检查 |
| 就绪探针 | ❌ 缺失 | |
| 启动探针 | ❌ 缺失 | |
| 优雅关闭 | ❌ 缺失 | 无信号处理 |
| 日志轮转 | ❌ 缺失 | 依赖容器 stdout |
| 敏感信息管理 | ⚠️ 部分 | .gitignore 存在但 .env.example 不完整 |

**主要问题**:
1. 无容器化配置，无法直接部署到 K8s
2. 无 CI/CD，无法自动化测试和部署
3. 无优雅关闭机制，可能导致评估中断

---

## 6. 发现的问题（分级）

### P0 - 阻塞生产使用

1. **测试覆盖不足**: 核心逻辑无单元测试保障
2. **批量端点无并发限制**: 可能导致资源耗尽

> 认证、限流、幂等性由 infra 层管理，不纳入应用层问题。

### P1 - 影响可维护性

1. **错误码不规范**: `LLM_BAD_REQUEST` 返回 500 应该是 400
2. **日志非结构化**: 生产环境难以分析和告警
3. **health 端点过于简单**: 无法检测真实服务状态

> 容器化和 CI/CD 由 infra 层管理，不纳入应用层问题。

### P2 - 影响扩展性

1. **无异步回调机制**: 长时间评估需要轮询
2. **prompt.yaml 管理分散**: 与代码分离，维护困难
3. **配置热更新缺失**: 修改配置需要重启
4. **数据库索引缺失**: 历史查询性能问题
5. **无 metrics 收集**: 无法观测服务性能

### P3 - 优化建议

1. **feature flag 缺失**: 无法灰度发布新 metric
2. **多环境配置管理缺失**: 开发/生产环境配置混在一起
3. **无 API 文档自动发布**: 依赖 Swagger UI 实时生成

---

## 7. 改进路线图建议

### Phase 1 - 代码质量与稳定性（1-2 周）

**目标**: 达到生产可用的代码质量标准

1. 完善 error code（修复 500→400）
2. 添加基础单元测试（registry 层）
3. 添加批量端点并发限制（Semaphore）

### Phase 2 - 可观测性（1 周）

**目标**: 具备生产问题排查能力

1. 结构化日志（JSON 格式 + trace ID）
2. 添加 Prometheus metrics
3. 增强 health 端点（DB + LLM 连通性）
4. 添加分布式追踪（OpenTelemetry）

### Phase 3 - 部署配合（按需）

**目标**: 配合 infra 层完成部署

1. 添加优雅关闭机制
2. 配合 infra 层的健康检查需求
3. 确保日志格式符合 infra 收集要求

> Dockerfile、CI/CD、容器编排由 infra 层管理。

### Phase 4 - 扩展性增强（2 周）

**目标**: 支持大规模生产场景

1. 实现异步回调机制（WebSocket 或 webhook）
2. prompt 管理优化（考虑 DB 或配置中心）
3. 数据库索引优化
4. 配置热更新（通过 reload endpoint）
5. 添加性能测试和基准

---

## 8. 结论

该项目在**核心架构设计**上表现良好，三层分离、注册表模式、动态路由等设计有效降低了扩展成本。作为内部评估服务已经可用。

作为**生产级中间件**，在可观测性和测试覆盖方面仍有提升空间。认证、限流、幂等性、容器化等由 infra 层统一管理，应用层需关注代码质量、错误处理和可观测性。

**关键改进优先级**:
1. 单元测试（P0）
2. 批量并发限制（P0）
3. 错误码规范（P1）
4. 可观测性（P1）

---

**审查人**: Claude (Architecture Review Agent)
**下次审查建议**: Phase 1 完成后重新评估
