首次启动按 `src/models/entities.py` 的 SQLAlchemy 定义建表。保留数据卷升级时先记录并验证具体迁移。

## 配料与缺口（2026-11）

新增 `sleeves.substitute_code` 列和 `fulfillment_lock`、`workstations`、`stock`、`requisitions`、`requisition_lines`、`reservations`、`issues`、`reconciliations` 表。已有 MySQL 数据卷需手工迁移（`create_all` 只建新表，不会给旧表加列）：

```sql
ALTER TABLE sleeves ADD COLUMN substitute_code VARCHAR(32) NULL;
CREATE TABLE fulfillment_lock (id INT PRIMARY KEY);
INSERT INTO fulfillment_lock (id) VALUES (1);
```

其余新表由应用启动时 `create_all` 自动建立；`fulfillment_lock` 的单行记录也会在启动时补建。迁移前请备份数据卷并先在副本上验证。
