# 槐页修复 · 无酸封套领用预测

槐页修复的 5 人材料组给照片、地图和手稿的修复工位供料。原流程从 `封套收据-2026.xlsx` 拷入月度表，再按上一月均量备料。工作组需要区分真实零领用与漏传，避免预测看到回测答案，并把预计领用换算成到货周期内可采购的包装数量。备料单给材料负责人核对后交采购员。

| 角色 | 常用页面 | 权限与动作 |
|---|---|---|
| `analyst` 档案备料员 | 规格账本、领用周序列、滚动回测 | 建规格、登记及补报、执行计算 |
| `manager` 材料负责人 | 领用备料单 | 分析员权限，另可签单和查询审计 |
| `viewer` 修复组观察员 | 四个模块 | 查阅与下载证据 |

## 周一工作剧本

1. 08:50 核对 `封套收据-2026.xlsx` 的 `SL-A4` 规格包规为 25 张，到货周期 3 周。
2. 09:05 比对 `SL-8X10`、`SL-MAP` 的包规、到货周数。
3. 09:30 在领用周序列查看各规格的独立台账。2026 年 10 月 19 日的 `SL-MAP` 为缺传。
4. 09:50 先提交地图封套，看回测拒绝把最近的缺传周当作零领取。
5. 10:00 材料员确认原始收据无领用，补报 0 张。
6. 10:20 提交 A4 备料测算，SBA 系数 0.20，移动平均窗口 8 周。结果展示各起点发生量及误差。
7. 10:45 材料负责人复核包数和用途后签核，回看此前缺传单保留的失败证据。
8. 11:00 下载 CSV 提供给采购，采购另行扣除库存与在途。

## 启动

```bash
cp .env.example .env
docker compose up --build --wait
docker compose exec -T backend python -m scripts.seed_demo
```

页面 `http://localhost:18277`，API 文档 `http://localhost:19277/docs`，MySQL 端口 `17777`。使用 `analyst@huaiye.demo`、`manager@huaiye.demo` 或 `viewer@huaiye.demo`，统一密码 `Archive2026!`。

| 服务 | 作用 |
|---|---|
| frontend | Nginx 1.27 托管原生 HTML/CSS/JS 和 `/api` 反代 |
| backend | Python 3.11、FastAPI、SQLAlchemy 校验写入、签核与导出 |
| worker | 数据库持久存储任务，Redis 唤醒，JSON 写入共享卷 |
| db | MySQL 8.0 保存规格、周记录、备料单、审计 |
| redis | Redis 7，健康探针与队列通知 |

`.env` 可覆盖 `FRONTEND_PORT`、`BACKEND_PORT`、`DB_PORT`、`JWT_SECRET`、`DB_PASSWORD`、`MYSQL_ROOT_PASSWORD` 与 `SEED_DEMO`。本地开发可用 `docker compose exec -T backend python -m compileall src`。结构定义和输入模型位于 `backend/src/models` 和 `schemas`，计算位于 `backend/src/services/forecast.py`，`frontend/src/pages` 按业务分页面。角色和任务状态出现在 `backend/src/constants/enums.py` / `frontend/src/constants/enums.js`、登录授权、任务切换和备料报告处；周状态见 `UsageInput` 及领用序列页。

## 口径与使用边界

每个规格从最近周向历史回溯至缺周或缺传。最近周缺传直接阻断。SBA 分别对正领用量和正领用之间的间隔做指数平滑，得到每周 `(1-α/2)×平滑领用量÷平滑间隔`。每个回测点向前训练，向后按完整到货周期汇总，移动均值用同一评估窗口；周期 MAE 较低的方法取得备料建议，得分完全相同时使用 SBA。包数使用周期估计数量除包规后向上取整。重叠的历史评估窗口用于方法比选，误差只代表本台账历史片段；点预测及备料包数还需结合库存和正在执行的修复任务。预置序列按固定日期与算式构造，可重复验证。

MIT License，见 `LICENSE`。
