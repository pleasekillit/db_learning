# 阶段 5 · PostgreSQL / TimescaleDB / JSONB / DuckDB 进阶

> 完成「先本地后集中」的跳跃：SQLite 学完概念后，换到服务端 PostgreSQL，
> 并给时序数据加上 TimescaleDB 分区能力。**关键验证点：业务代码不重写。**

## 本章目标
- 用 Docker 起 PostgreSQL，并把同一套代码换连接串跑通（验证零改动）。
- 学会给 `timeseries_points` 建 TimescaleDB hypertable，用 `time_bucket` 做趋势聚合。
- 理解 JSONB（PG）与 TEXT（SQLite）的差异，以及 DuckDB 旁挂分析 Parquet 波形。

## 对应代码位置

本章**不需要改业务代码**，改的是「配置」和「数据库端」：

| 内容 | 对应位置 |
| --- | --- |
| 换库连接串 | `powerdb/config.py` 的 `url`（或环境变量 `POWERDB_URL`） |
| JSON 方言自适应（TEXT↔JSONB） | `powerdb/models/common.py` 的 `JSONType` |
| 迁移入口（PG 也共用） | `powerdb/migrate/env.py` |
| 验证脚本 | 复用 `examples/seed_demo.py`（只换连接串） |

> 这就是当初选 SQLAlchemy 的价值兑现点：换库 = 改一个连接串。

## 基础知识详解

### 1. 从 SQLite 到 PostgreSQL
- SQLite：嵌入式单文件，无服务进程，适合单机/入门。
- PostgreSQL：独立服务端，多用户并发强、类型丰富、有 JSONB 等高级类型，适合集中部署 + 看板多人读。
- 连接串差异（你只需记住这一点）：
  ```
  sqlite:///powerdb.db
  postgresql+psycopg://user:password@127.0.0.1:5432/powerdb
  ```

### 2. TimescaleDB（时序扩展）
是 PG 的插件，核心概念是 **hypertable**（超表）：把大表按时间列自动切分成多个物理分块，
写入更快、按时间范围查询更高效。
```sql
SELECT create_hypertable('timeseries_points', 't');
SELECT time_bucket('1 second', t) AS bucket, avg(value)
FROM timeseries_points WHERE channel_id = 1 GROUP BY bucket ORDER BY bucket;
```

### 3. JSONB vs TEXT
- SQLite 里 JSON 被存成 `TEXT`，只能整存整取。
- PG 的 `JSONB` 是二进制 JSON，能在 SQL 里直接对 JSON 内部字段建索引和查询。
- 骨架用 `JSON().with_variant(JSONB(), "postgresql")` 自动适配：SQLite 存 TEXT、PG 存 JSONB，业务无感。

### 4. DuckDB（列式分析）
不是主库，是「分析引擎」。高频原始波形存成 Parquet 后，可以用 DuckDB 一条 SQL 极速聚合，
适合海量历史数据的横向对比与 AI 数据准备，且不干扰主库。

## 训练 Demo 详解

**任务一（Docker 起 PG）**：
```bash
docker run -d --name pg-powerdb \
  -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=powerdb \
  -p 5432:5432 postgres:16
```

**任务二（换连接串，零改动验证）**：
```bash
cd /workspace/powerdb
export POWERDB_URL="postgresql+psycopg://postgres:postgres@127.0.0.1:5432/powerdb"
python3 examples/seed_demo.py
python3 -m pytest -q
```
观察输出与 SQLite 阶段完全一致 → 证明业务代码零改造。

**任务三（时序 hypertable）**：安装 TimescaleDB 镜像，对 `timeseries_points` 建 hypertable，
用 `time_bucket` 写一条趋势聚合 SQL，对比用 PG 原生表的效果。

**任务四（DuckDB）**：把一个 Parquet 波形文件用 DuckDB 读进来算均值/最大值。

**验证标准**：同一份 `seed_demo.py` 在 SQLite 与 PG 都能跑，差异只在一行连接串。

## 官方文档链接
- PostgreSQL 官方文档：https://www.postgresql.org/docs/
- psycopg（PG Python 驱动）：https://www.psycopg.org/psycopg3/docs/
- TimescaleDB 文档：https://docs.timescale.com/
- SQLAlchemy PostgreSQL 方言：https://docs.sqlalchemy.org/en/20/dialects/postgresql.html
- PostgreSQL JSONB：https://www.postgresql.org/docs/current/datatype-json.html
- DuckDB 文档：https://duckdb.org/docs/

## 学习笔记

### 日常踩坑记录（Pitfalls）
| 日期 | 现象/问题 | 原因 | 解决/结论 |
| --- | --- | --- | --- |
| 示例 | 换 PG 后报 driver 缺失 | 没装 `psycopg[binary]` | `pip install "psycopg[binary]>=3.1"` |
| 示例 | JSON 字段在 PG 下按 JSON 语法查不生效 | SQLite 存的是 TEXT | 记住迁移后有 JSONB 能力 |
|  |  |  |  |

### 学习待办（Todo）
- [ ] Docker 起 PG 并换连接串跑通 seed_demo + pytest
- [ ] 建 hypertable + 用 time_bucket 写一条趋势聚合
- [ ] 用 DuckDB 对一份 Parquet 波形做一次聚合