# Order Notification Canonical Dev Spec

<!-- EDS:MANIFEST:BEGIN -->
```json
{
  "schema": "easy-dev-spec/v1",
  "spec_id": "order-notification-2026",
  "revision": 1,
  "status": "READY",
  "title": "Order Notification",
  "repositories": [
    {
      "repo_id": "R1",
      "name": "order-service",
      "remote_urls": ["git@example.com:demo/order-service.git"],
      "path_hint": "/workspace/order-service",
      "baseline": {"ref": "main", "commit": "1111111111111111111111111111111111111111"},
      "tech_stack": ["Java 17", "Maven"],
      "section_id": "repo-r1"
    },
    {
      "repo_id": "R2",
      "name": "notification-service",
      "remote_urls": ["https://example.com/demo/notification-service.git"],
      "path_hint": "/workspace/notification-service",
      "baseline": {"ref": "main", "commit": "2222222222222222222222222222222222222222"},
      "tech_stack": ["Java 17", "Maven"],
      "section_id": "repo-r2"
    }
  ],
  "contracts": [
    {
      "contract_id": "C1",
      "name": "OrderCreatedEvent",
      "owner_task_id": "R1-T1",
      "consumer_task_ids": ["R2-T1"],
      "section_id": "contract-c1"
    }
  ],
  "tasks": [
    {
      "task_id": "R1-T1",
      "repo_id": "R1",
      "title": "Publish order event",
      "status": "READY",
      "section_id": "task-r1-t1",
      "depends_on": [],
      "change_ids": ["F1"],
      "step_ids": ["S1"],
      "test_ids": ["T1"]
    },
    {
      "task_id": "R2-T1",
      "repo_id": "R2",
      "title": "Consume order event",
      "status": "READY",
      "section_id": "task-r2-t1",
      "depends_on": [
        {"task_id": "R1-T1", "type": "contract", "required_evidence": "C1 signature is frozen in revision 1"}
      ],
      "change_ids": ["F2"],
      "step_ids": ["S2"],
      "test_ids": ["T2"]
    },
    {
      "task_id": "R1-T2",
      "repo_id": "R1",
      "title": "Expose delivery status",
      "status": "READY",
      "section_id": "task-r1-t2",
      "depends_on": [
        {"task_id": "R1-T1", "type": "hard", "required_evidence": "OrderEventPublisherTest passes"},
        {"task_id": "R2-T1", "type": "integration", "required_evidence": "Consumer contract test passes before end-to-end verification"}
      ],
      "change_ids": ["F3"],
      "step_ids": ["S3"],
      "test_ids": ["T3"]
    }
  ],
  "changes": [
    {
      "change_id": "F1",
      "task_id": "R1-T1",
      "repo_id": "R1",
      "module": "order-domain",
      "path": "order-domain/src/main/java/com/example/order/OrderEventPublisher.java",
      "action": "add",
      "symbols": ["OrderEventPublisher#publish"]
    },
    {
      "change_id": "F2",
      "task_id": "R2-T1",
      "repo_id": "R2",
      "module": "notification-app",
      "path": "notification-app/src/main/java/com/example/notification/OrderEventConsumer.java",
      "action": "add",
      "symbols": ["OrderEventConsumer#onMessage"]
    },
    {
      "change_id": "F3",
      "task_id": "R1-T2",
      "repo_id": "R1",
      "module": "order-api",
      "path": "order-api/src/main/java/com/example/order/api/DeliveryStatusController.java",
      "action": "add",
      "symbols": ["DeliveryStatusController#getStatus"]
    }
  ],
  "steps": [
    {"step_id": "S1", "task_id": "R1-T1", "change_ids": ["F1"], "depends_on_step_ids": [], "test_ids": ["T1"]},
    {"step_id": "S2", "task_id": "R2-T1", "change_ids": ["F2"], "depends_on_step_ids": [], "test_ids": ["T2"]},
    {"step_id": "S3", "task_id": "R1-T2", "change_ids": ["F3"], "depends_on_step_ids": [], "test_ids": ["T3"]}
  ],
  "tests": [
    {"test_id": "T1", "task_id": "R1-T1", "file": "order-domain/src/test/java/com/example/order/OrderEventPublisherTest.java", "command": "mvn -Dtest=OrderEventPublisherTest test"},
    {"test_id": "T2", "task_id": "R2-T1", "file": "notification-app/src/test/java/com/example/notification/OrderEventConsumerTest.java", "command": "mvn -Dtest=OrderEventConsumerTest test"},
    {"test_id": "T3", "task_id": "R1-T2", "file": "order-api/src/test/java/com/example/order/api/DeliveryStatusControllerTest.java", "command": "mvn -Dtest=DeliveryStatusControllerTest test"}
  ]
}
```
<!-- EDS:MANIFEST:END -->

<!-- EDS:SECTION:BEGIN id=global-context -->
## 1. 全局约束

- 总目标：订单成功提交后发布事件，通知服务消费同一冻结契约。
- 成功指标：每个订单只产生一次通知，三个任务的测试和全链路验收均通过。
- 输入与证据：`OrderApplicationService#createOrder`、`NotificationSender#send` 和当前测试代码。
- 范围：订单事件生产、通知消费和投递状态查询。
- 非目标：不修改通知模板内容，原因是模板不属于订单事件协议。
- 兼容约束：C1 revision 1 字段保持向后兼容，新增字段只能可选。
- 安全与性能约束：所有入口保留原有鉴权，事件 ID 是全链路幂等键。
- 已关闭架构决策：事件由订单服务定义，通知服务只消费，无开放决策。
<!-- EDS:SECTION:END id=global-context -->

<!-- EDS:SECTION:BEGIN id=contract-c1 -->
## 2. 共享契约 C1：OrderCreatedEvent

- 定义方任务：`R1-T1`；消费方任务：`R2-T1`。
- package：`com.example.contract.order`。
- 完整 Java 签名：`public record OrderCreatedEvent(String eventId, String orderId, Instant occurredAt) {}`。
- 字段类型和空值：三个字段均为非空；空值抛出 `IllegalArgumentException`。
- 异常：生产失败抛出 `OrderEventPublishException`，消费失败交由消息客户端重试三次。
- 调用方：`OrderApplicationService#createOrder`；实现方：`OrderEventPublisher#publish` 和 `OrderEventConsumer#onMessage`。
- 兼容策略：revision 1 冻结字段名与 ISO-8601 时间语义，新增字段只能可选。
<!-- EDS:SECTION:END id=contract-c1 -->

<!-- EDS:SECTION:BEGIN id=repo-r1 -->
## 3. 仓库 R1：order-service

- 职责边界：提交订单、发布 C1、读取投递状态；不发送通知。
- normalized remote：`git@example.com:demo/order-service.git`。
- 基线：`main@1111111111111111111111111111111111111111`。
- 技术栈与本地规范：Java 17、Maven，遵守仓库 AGENTS.md。
- 当前代码证据：`OrderApplicationService#createOrder` 在事务提交后返回，尚未发布领域事件。
- 本仓库任务与波次：`R1-T1` 为波次 1；`R1-T2` 在 hard 证据满足后进入波次 2。
<!-- EDS:SECTION:END id=repo-r1 -->

<!-- EDS:SECTION:BEGIN id=repo-r2 -->
## 4. 仓库 R2：notification-service

- 职责边界：消费 C1 并创建通知；不修改订单状态。
- normalized remote：`https://example.com/demo/notification-service.git`。
- 基线：`main@2222222222222222222222222222222222222222`。
- 技术栈与本地规范：Java 17、Maven，遵守仓库 AGENTS.md。
- 当前代码证据：`NotificationSender#send` 已支持以业务键去重，但没有订单事件入口。
- 本仓库任务与波次：C1 冻结后，`R2-T1` 与订单服务编码并行。
<!-- EDS:SECTION:END id=repo-r2 -->

<!-- EDS:SECTION:BEGIN id=task-r1-t1 -->
## 5. 任务 R1-T1：发布订单事件

### 5.1 目标、交付物与非目标

- 目标与交付物：事务成功后发布一次 C1，并新增发布器。
- 非目标：通知内容由 R2 负责，本任务不修改模板。

### 5.2 文件与符号级改动

`F1` 在仓库 `R1`、模块 `order-domain` 的 `order-domain/src/main/java/com/example/order/OrderEventPublisher.java` 执行 add，新增 `OrderEventPublisher#publish`。

### 5.3 调用链 Diff

- 入口 `OrderApplicationService#createOrder`：改造前为 `createOrder -> OrderRepository#save -> return`；改造后为 `createOrder -> OrderRepository#save -> OrderEventPublisher#publish -> return`。发布失败抛出业务异常并回滚事务。

### 5.4 新增或修改类型契约

- package：`com.example.order`。
- 完整 Java 签名：`public interface OrderEventPublisher { void publish(OrderCreatedEvent event) throws OrderEventPublishException; }`。
- 字段类型与空值：参数类型为 `OrderCreatedEvent` 且不可为 null。
- 异常：客户端失败统一转换为 `OrderEventPublishException`。
- 调用方：`OrderApplicationService#createOrder`；实现方：`DefaultOrderEventPublisher#publish`。

### 5.5 存储、消息与配置闭环

- DDL、DO、Mapper、Repo：不新增持久化结构；依据是事件在现有订单事务提交点同步发送，订单读取仍由 `OrderRepository#save` 完成。
- 消息：`order.created.v1` producer 写入 `eventId` 作为幂等键；客户端执行三次指数退避，最终失败回滚。
- 配置：`order.event.topic` 类型 String，默认 `order.created.v1`；关闭开关时由发布器返回明确的 disabled 结果供灰度回退。

### 5.6 符号级实施步骤

- `S1`：在 `OrderApplicationService#createOrder` 的 `OrderRepository#save` 成功之后调用 `OrderEventPublisher#publish`；输入已持久化订单，输出 void，失败抛出 `OrderEventPublishException` 并回滚。绑定 `F1` 和 `T1`。

### 5.7 测试映射

- `T1` 覆盖 `S1`，测试文件 `order-domain/src/test/java/com/example/order/OrderEventPublisherTest.java`；场景：成功发布、null 事件和客户端失败；Mock 边界：只 Mock 消息客户端；命令 `mvn -Dtest=OrderEventPublisherTest test`；证据为三个断言通过。

### 5.8 风险、回退与完成证据

- 风险是消息延迟增加请求耗时；监控 publisher latency。回退时关闭 `order.event.enabled` 并恢复原调用链。完成证据为 F1 存在且 T1 命令通过。
<!-- EDS:SECTION:END id=task-r1-t1 -->

<!-- EDS:SECTION:BEGIN id=task-r2-t1 -->
## 6. 任务 R2-T1：消费订单事件

### 6.1 目标、交付物与非目标

- 目标与交付物：新增 C1 consumer 并调用已有发送器。
- 非目标：本任务不定义 C1，也不修改订单服务。

### 6.2 文件与符号级改动

`F2` 在仓库 `R2`、模块 `notification-app` 的 `notification-app/src/main/java/com/example/notification/OrderEventConsumer.java` 执行 add，新增 `OrderEventConsumer#onMessage`。

### 6.3 调用链 Diff

- 入口 `OrderEventConsumer#onMessage`：改造前不存在订单事件入口；改造后为 `onMessage -> NotificationSender#send -> Ack`，发送失败返回 Nack 触发客户端重试。

### 6.4 新增或修改类型契约

- package：`com.example.notification`。
- 完整 Java 签名：`public final class OrderEventConsumer { public ConsumeResult onMessage(OrderCreatedEvent event); }`。
- 字段类型与空值：事件类型为 C1 且不可为 null，缺失字段返回不可重试拒绝。
- 异常：`TransientNotificationException` 返回 Nack，契约异常返回 Reject。
- 调用方：消息客户端 adapter；实现方：`OrderEventConsumer#onMessage`。

### 6.5 存储、消息与配置闭环

- DDL、DO、Mapper、Repo：不新增表；依据是现有 `NotificationDedupRepository#insertIfAbsent` 已按业务键持久化幂等记录。
- 消息：消费 `order.created.v1`，使用 `eventId` 调用 `insertIfAbsent`；临时失败重试三次，契约失败进入死信。
- 配置：`notification.order.consumer.enabled` 类型 boolean，默认 false；灰度开启，回退为 false 并保留积压消息。

### 6.6 符号级实施步骤

- `S2`：在 `OrderEventConsumer#onMessage` 首行校验 C1，再在 `NotificationSender#send` 前调用幂等 Repo；输入 `OrderCreatedEvent`，返回 Ack/Nack/Reject。绑定 `F2` 和 `T2`。

### 6.7 测试映射

- `T2` 覆盖 `S2`，测试文件 `notification-app/src/test/java/com/example/notification/OrderEventConsumerTest.java`；场景：首次事件、重复事件、临时失败和坏契约；Mock 边界：消息 ack adapter 与外部发送通道，不 Mock 幂等判断；命令 `mvn -Dtest=OrderEventConsumerTest test`；证据为四类结果断言通过。

### 6.8 风险、回退与完成证据

- 风险是重复通知；监控 dedup conflict 和发送计数。回退时关闭 consumer 开关并保留消息。完成证据为 F2 存在且 T2 命令通过。
<!-- EDS:SECTION:END id=task-r2-t1 -->

<!-- EDS:SECTION:BEGIN id=task-r1-t2 -->
## 7. 任务 R1-T2：查询投递状态

### 7.1 目标、交付物与非目标

- 目标与交付物：新增订单投递状态只读接口。
- 非目标：不提供通知服务内部重放操作。

### 7.2 文件与符号级改动

`F3` 在仓库 `R1`、模块 `order-api` 的 `order-api/src/main/java/com/example/order/api/DeliveryStatusController.java` 执行 add，新增 `DeliveryStatusController#getStatus`。

### 7.3 调用链 Diff

- 入口 `GET /orders/{id}/delivery-status`：改造前不存在；改造后为 `DeliveryStatusController#getStatus -> DeliveryStatusQuery#get -> response`，不存在订单返回 404。

### 7.4 新增或修改类型契约

- package：`com.example.order.api`。
- 完整 Java 签名：`public DeliveryStatusResponse getStatus(@NotBlank String orderId)`。
- 字段类型与空值：orderId 是非空 String，response 字段 `delivered` 是 boolean。
- 异常：订单不存在抛出 `OrderNotFoundException` 并映射 HTTP 404。
- 调用方：订单查询 HTTP 客户端；实现方：`DeliveryStatusController#getStatus`。

### 7.5 存储、消息与配置闭环

- DDL、DO、Mapper、Repo：读取现有 `OrderRepository#findById`，不新增字段；依据是本任务返回消息发布状态而非通知送达状态。
- 消息：本任务不生产或消费消息；依据是入口只查询 R1 已有订单和发布结果。
- 配置：不修改配置；依据是 `DeliveryStatusController#getStatus` 继续使用现有 API 鉴权链，任务级回退为移除新路由。

### 7.6 符号级实施步骤

- `S3`：新增 `DeliveryStatusController#getStatus`，在参数校验后调用 `DeliveryStatusQuery#get` 并映射 200/404；输入 orderId，输出 `DeliveryStatusResponse`。绑定 `F3` 和 `T3`。

### 7.7 测试映射

- `T3` 覆盖 `S3`，测试文件 `order-api/src/test/java/com/example/order/api/DeliveryStatusControllerTest.java`；场景：已发布、未发布、订单不存在和空 ID；Mock 边界：只 Mock `DeliveryStatusQuery`；命令 `mvn -Dtest=DeliveryStatusControllerTest test`；证据为 HTTP 状态和响应体断言通过。

### 7.8 风险、回退与完成证据

- 风险是状态语义被误解；响应字段文档明确只代表事件发布。回退时移除路由。完成证据为 F3 存在且 T3 命令通过。
<!-- EDS:SECTION:END id=task-r1-t2 -->

<!-- EDS:SECTION:BEGIN id=integration-plan -->
## 8. 联调计划

| 波次 | 前置任务及依赖类型 | 参与任务 | 联调入口 | 契约 / 数据 | 完成证据 |
| --- | --- | --- | --- | --- | --- |
| 1 | 无 | `R1-T1` | `OrderApplicationService#createOrder` | `C1` | `OrderEventPublisherTest` 通过 |
| 1 | `R1-T1` contract | `R2-T1` | `OrderEventConsumer#onMessage` | `C1` | consumer contract test 通过 |
| 2 | `R1-T1` hard、`R2-T1` integration | `R1-T2` | `GET /orders/{id}/delivery-status` | 订单发布状态 | GET 接口测试通过且消息联调完成 |
<!-- EDS:SECTION:END id=integration-plan -->

<!-- EDS:SECTION:BEGIN id=rollout-plan -->
## 9. 发布与回退

- 发布顺序：先发布关闭开关的 `R2` consumer，再发布 `R1` producer，最后发布 `R1` 查询接口。
- 配置 / DDL / 消息切换顺序：无 DDL；先保持 consumer 配置关闭，再发布消息 producer，确认积压后灰度开启 consumer。
- 兼容窗口：C1 revision 1 在 R1 和 R2 全部稳定前保持双版本可读。
- 全链路回退触发条件与动作：异常时先关闭 producer 和 consumer 配置，保留消息积压并回滚对应应用版本。
<!-- EDS:SECTION:END id=rollout-plan -->

<!-- EDS:SECTION:BEGIN id=end-to-end-acceptance -->
## 10. 全链路验收

| 验收 ID | 覆盖任务 | 场景 | 前置数据 / Mock 边界 | 执行命令或入口 | 通过标准 |
| --- | --- | --- | --- | --- | --- |
| `E2E-1` | `R1-T1`、`R2-T1`、`R1-T2` | 创建订单、消费 C1 并查询投递状态 | 使用测试 topic 和真实幂等存储，只 Mock 外部短信网关 | 创建订单入口、consumer trace 和 GET 查询入口 | 只产生一个 C1 和一次通知，查询返回事件已发布，三个任务测试命令均通过 |
<!-- EDS:SECTION:END id=end-to-end-acceptance -->
