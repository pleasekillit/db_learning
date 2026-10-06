# 阶段 2 · 用 Python 访问数据库

> 从「命令行 SQL」过渡到「Python 访问」，并理解为什么要用 ORM。
> 你最终写业务时不会手写 SQL 字符串，而是用 ORM 对象——但本阶段要先亲手体会三者的差异。

## 本章目标

- 会用原生 `sqlite3` 写一条查询（感受手写 SQL 的繁琐）。
- 会用 SQLAlchemy **Core**（SQL 表达式）和 **ORM**（对象映射）各实现一次读写。
- 理解 Session / 事务 / commit / rollback。

## 对应代码位置

本阶段最终会落在骨架的这一块：

| 内容               | 对应代码                                                            |
|------------------|-----------------------------------------------------------------|
| Session 工厂与事务上下文 | `powerdb/core/engine.py` 里的 `session_scope()` / `init_engine()` |
| 引擎/连接配置          | `powerdb/config.py`                                             |
| ORM 模型（对象↔表）     | `powerdb/models/*.py`                                           |
| 端到端读写示例          | `examples/seed_demo.py`                                         |

> 你可以在 `examples/seed_demo.py` 里看到 `session_scope()` + `session.add(...)` 的真实用法，
> 本阶段先读它、再看下面三种"手写版"对比。

## 基础知识详解

### 1. 原生 sqlite3（最底层，手写 SQL）

```python
import sqlite3

conn = sqlite3.connect("demo.db")
cur = conn.cursor()
cur.execute(
    "INSERT INTO measurements (test_record_id, metric, value, unit) VALUES (?, ?, ?, ?)",
    (1, "efficiency", 97.2, "%"),
)
conn.commit()
cur.execute("SELECT value, unit FROM measurements WHERE metric = ?", ("efficiency",))
print(cur.fetchall())  # [(97.2, '%')]
conn.close()
```

- 优点：标准库自带、零依赖。
- 缺点：手写 SQL 字符串、绑定参数容易写错列、换数据库方言要改 SQL、无类型安全。

### 2. SQLAlchemy Core（SQL 表达式，中间层）

```python
from sqlalchemy import create_engine, insert, select, Table, MetaData, Column, String, Float, Integer

engine = create_engine("sqlite:///demo.db")
metadata = MetaData()
measurements = Table(
    "measurements", metadata,
    Column("test_record_id", Integer), Column("metric", String),
    Column("value", Float), Column("unit", String),
)
with engine.begin() as conn:
    conn.execute(insert(measurements).values(test_record_id=1, metric="efficiency", value=97.2, unit="%"))
    rows = conn.execute(select(measurements).where(measurements.c.metric == "efficiency"))
    print(rows.fetchall())
```

- 优点：用 Python 对象表达 SQL，`WHERE` 写成 `where(measurements.c.metric == "efficiency")`。
- 缺点：仍在操作"表"，重点是 SQL 表达式而非业务对象。

### 3. SQLAlchemy ORM（对象映射，骨架采用的方式）

ORM 把「行」映射成「对象」，你操作对象，框架自动生成 SQL（这就是 `models/` 里那些类的作用）。

### 4. Session 与事务

- `Session`：一次与数据库交互的工作单元，负责跟踪对象变化。
- `commit`：把本次改动落盘；`rollback`：撤销本次改动。
- 骨架把这一套封装成 `session_scope`：正常退出自动 commit，异常自动 rollback，最后 close。

## 训练 Demo 详解

**任务一**：用三种方式各实现一次「插入 + 查询一条 Measurement」，体会差异。

**任务二**：跑通骨架端到端示例：

```bash
cd /workspace/powerdb
python3 examples/seed_demo.py
```

观察输出里的「横向对比 efficiency」与「概要统计」，然后在 `seed_demo.py` 里找到：

- `with session_scope() as session:` —— 事务边界；
- `session.add(...)` / `session.flush()` —— 写入与拿到 id；
- `compare_metric(...)` —— 后续阶段要深入的服务层查询。

**任务三**：自己写一个 5 行小脚本，用 `session_scope` 插入一条 `Project` 并查回来。

**验证标准**：能说清楚「ORM 帮我们屏蔽了哪些 SQLite/PG 方言差异」「commit 没执行会发生什么」。

## 官方文档链接

- Python 标准库 sqlite3：https://docs.python.org/3/library/sqlite3.html
- SQLAlchemy ORM 快速入门：https://docs.sqlalchemy.org/en/20/orm/quickstart.html
- SQLAlchemy Core 教程：https://docs.sqlalchemy.org/en/20/core/tutorial.html
- Session 基础：https://docs.sqlalchemy.org/en/20/orm/session_basics.html
- 引擎与会话配置：https://docs.sqlalchemy.org/en/20/core/engines.html

## 学习笔记

### 日常踩坑记录（Pitfalls）

| 日期         | 现象/问题                     | 原因                                                | 解决/结论                  |
|------------|---------------------------|---------------------------------------------------|------------------------|
| 示例         | 插入了数据但下次查不到               | 忘了 `commit`/事务未提交                                 | 用 `session_scope` 统一收口 |
| 示例         | `fetchall()` 返回多行却只想要一行报错 | 用了 `scalar` 但结果非唯一                                | 确认过滤条件唯一，或用 `.first()` |
| 2026-10-06 | 问题1：环境变量                  | `config.py`中的`DatabaseConfig` 类使用了os.environ的取值方式 | 详见问题1                  |
| 2026-10-06 | 问题2：弥补SQLite外键检查          | 原本的SQLite3是不支持外键检查的，该项目的`engine.py`加上了            | 详见问题2                  |

#### 问题1：环境变量

- `.env` 文件 +`load_dotenv()`方式做到可配置

> 用 .env 文件
> 安装`python-dotenv` 后，在项目根放一个`.env` 文件：

```ini
POWERDB_URL = postgresql+psycopg://user:pass@127.0.0.1:5432/powerdb
POWERDB_ECHO = 1
```

> 代码里加一行`load_dotenv()` ，就会自动把`.env` 里的变量加载到`os.environ` ：

```python
from dotenv import load_dotenv

load_dotenv()  # 放在程序入口最顶部
```

#### 问题2：弥补SQLite外键检查

- 原本SQLite3没有默认的外键检查，这会导致一些脏数据生成，因此该项目的`engine.py`做了外键检查加强

```python
def init_engine(config: DatabaseConfig | None = None) -> Engine:
    """初始化全局引擎（应用启动时调用一次）。"""
    global _engine, _SessionFactory
    config = config or DatabaseConfig()
    _engine = _build_engine(config)

    if config.url.startswith("sqlite"):
        # 让 SQLite 也遵守外键约束（默认是关闭的）
        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragma(dbapi_conn: Any, _: Any) -> None:
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
```

> 表格链条如下

```text
Project → Sample → TestRun → TestRecord → Measurement
                                      └─ test_record_id 指向 test_records.id
```

> 为了避免产生孤儿数据，需要通过`PRAGMA foreign_keys=ON`启用外键检查

### 学习待办（Todo）

- [ ] 用 sqlite3 / Core / ORM 各写一遍「插入+查询」
- [ ] 跑通 `seed_demo.py` 并找到 3 处关键代码
- [ ] 实验：在 `session_scope` 里故意抛异常，观察是否 rollback