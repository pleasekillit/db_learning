# 附录 · SQLAlchemy 关键方法速查（原理 + 排查）

> 目的：把项目里用到的 SQLAlchemy 方法逐个说清楚「做什么 / 背后原理 / 生成什么 SQL / 出问题时怎么查」。
> 适合在阶段2/3 之后、写业务或排障时随时翻。
> 每个方法都标注了**本项目实际用到它的文件**，可回代码对照。

## 0. 怎么观察底层 SQL（排查的第一手段）

原理：SQLAlchemy 本质是把你的 Python 对象「编译」成 SQL 字符串，再让 DBAPI 执行。
所以排查问题 = 先看到它到底发了什么 SQL。

```python
# 手段1：echo=True，每条 SQL + 参数都会打印
#        —— 见 powerdb/core/engine.py 的 _build_engine(echo=config.echo)
#        —— 把 config 里的 echo 打开即可全量打印

# 手段2：直接打印一条语句会编译成的 SQL（不真正执行）
from sqlalchemy import select
from powerdb.models.result import Measurement

stmt = select(Measurement).where(Measurement.metric == "efficiency")
print(stmt)   # 打印会触发自动编译，看到完整 SELECT 文本
```

> 记住一句话：**你看不懂一个查询时，先 `print(stmt)` 或开 `echo=True`，把生成的 SQL 拿到 sqlite3/数据库里复现。**
> 90% 的问题在「看到真实 SQL」那一刻就解决了。

---

## 1. 引擎 / 连接层（Engine）

### `create_engine(url, echo=False, pool_size=5, pool_recycle=-1, connect_args=None)`
- **做什么**：根据连接串创建一个 Engine（连接池）。SQLite 用 `sqlite:///文件路径`，PostgreSQL 用 `postgresql+psycopg://user:pwd@host/db`。
- **原理**：**懒连接**——创建 Engine 时不连库，第一次 `execute` 才真正建立 DBAPI 连接；之后连接放回池里复用。
- **排查点**：
  - `echo=True`：打印所有 SQL（含绑定参数），性能/逻辑排查的万能开关。
  - `pool_recycle`：长连接超过 N 秒自动回收重建，防止 MySQL/PG 服务器掐断空闲连接（`-1` 表示不回收）。
  - SQLite 跨线程：要传 `connect_args={"check_same_thread": False}`，否则多线程访问同一文件报错。
- **项目位置**：[core/engine.py](../powerdb/powerdb/core/engine.py) 的 `_build_engine()`。

### `event.listens_for(engine, "connect")`
- **做什么**：注册一个「每次新建连接时」的回调。
- **原理**：SQLAlchemy 事件钩子；回调函数拿到的 `dbapi_conn` 是底层连接，可直接执行 `PRAGMA`。
- **本项目用途**：SQLite **默认关闭外键约束**，须在每个连接上执行 `PRAGMA foreign_keys=ON` 才生效。
- **排查点**：外键插了垃圾数据、`delete` 父表子表没反应 → 检查这个 PRAGMA 是否真的执行了。
- **项目位置**：[core/engine.py](../powerdb/powerdb/core/engine.py) 的 `init_engine()`。

---

## 2. 会话 / 事务层（Session）

> 这是最容易踩坑的一层。核心概念：**对象的 4 种状态**——
> `transient`（刚 new）→ `pending`（`add` 后）→ `persistent`（`flush`/`commit` 后）→ `detached`（`close` 后）。

### `sessionmaker(bind=engine, expire_on_commit=False) -> Session工厂`
- **原理**：一个工厂，`工厂()` 每次新建一个 `Session`。项目把工厂缓存成全局 `_SessionFactory`。
- **`expire_on_commit=False` 很关键**：默认 `True` 时，`commit` 后对象属性会被标记"过期"，下次访问会偷偷发一条 SELECT 重新取。项目设 `False`，让 commit 后对象还能直接用、不发多余查询。
- **排查点**：如果发现 commit 之后访问属性变 `None` 或莫名发 `SELECT`，就是 `expire_on_commit` 在作怪。
- **项目位置**：[core/engine.py](../powerdb/powerdb/core/engine.py) `init_engine()`。

### `session_scope()`（项目自封装）
- **原理**：`@contextmanager`，`yield` 一个会话 → 正常退出 `commit` → 异常 `rollback` → 最后 `close`。把"事务边界"统一收口。
- **排查点**：`close` 之后这个 session 及其加载对象就 `detached` 了，**不要再访问对象的关系属性**，否则报 `DetachedInstanceError`。
- **项目位置**：[core/engine.py](../powerdb/powerdb/core/engine.py) `session_scope()`。

### `session.add(obj)` / `add_all(objs)`
- **做什么**：把对象标记为「待写入」。**此时不发 SQL**。
- **原理**：对象进入 `pending`，真正的 `INSERT` 要等 `flush()` 或 `commit()`。
- **排查点**：以为 add 了就入库、结果没查回来 → add 只是登记，要 commit。

### `session.flush()`
- **做什么**：立即把 pending 变更生成 SQL 发给数据库，**但不提交事务**。
- **原理**：flush 是"把内存变更刷到数据库会话里"，commit 才是"提交事务/落盘"。flush 会**回填主键 id**。
- **关键用途**：先插父表拿到 `parent.id`，再拿这个 id 插子表——项目在 `api/app.py` 的 `submit_run` 里 flush 拿 `run.id` 再插记录。
- **排查点**：flush 失败会抛 `IntegrityError` 且事务进入待回滚状态，需 `rollback`。

### `session.commit()`
- **做什么**：`flush() + 提交事务`（DBAPI `connection.commit()`），让改动真正落盘、其他连接可见。
- **排查点**：commit 后事务结束，同个 session 可继续开新事务。

### `session.rollback()`
- **做什么**：撤销本事务所有未提交改动，把 pending 对象重置。
- **排查点**：一次失败后不 rollback，后续操作会一直报"上一个事务已失败"。

### `session.close()`
- **做什么**：把连接归还连接池、释放事务资源。**不是删除数据、也不是销毁对象**（对象变成 detached）。

### `session.get(Model, pk)`
- **做什么**：按主键取一行，没有返回 `None`。
- **原理**：先查 identity map（本次会话已加载过就直接返回，不发 SQL）。
- **项目位置**：[repositories/base.py](../powerdb/powerdb/repositories/base.py) `get()`。

### `session.scalar(stmt)` ← 高频
- **做什么**：执行查询，返回**第一行的第一列**（一个标量）。
- **排查点**：结果**多于一行会抛 `MultipleResultsFound`**；没结果返回 `None`。适合 `count`、按唯一条件取单值。
- **项目位置**：[repositories/base.py](../powerdb/powerdb/repositories/base.py) `get_by()` / `count()`、`maintenance.py` `stats()`。

### `session.scalars(stmt)` ← 高频
- **做什么**：执行查询，返回**每行第一列**组成的迭代器（`list(...)` 转列表）。
- **排查点**：`select(Model)` 配 `scalars()` 得到实体列表；配错（如 select 多列）会只取第一列丢数据。
- **项目位置**：[repositories/base.py](../powerdb/powerdb/repositories/base.py) `list()`、[repositories/timeseries_repository.py](../powerdb/powerdb/repositories/timeseries_repository.py)。

### `session.execute(stmt)` ← 万能
- **做什么**：执行任意语句（SELECT / INSERT / UPDATE / DELETE），返回 `Result`。
- **原理**：`Result` 是流式结果，配合下面几个取值方法使用：

| 取值方法 | 返回 | 说明 |
| --- | --- | --- |
| `.scalars()` | 每行第一列 | 取实体/标量 |
| `.mappings()` | 每行一个 dict | 取多列字典，项目横向对比用它 |
| `.first()` | 第一行 | 无结果返回 None，不报错 |
| `.one()` | 唯一一行 | 0 行报错、多行也报错（严格） |
| `.one_or_none()` | 唯一或 None | 多行报错 |
| `.all()` | 全部 | 注意内存 |

- **项目位置**：[repositories/result_repository.py](../powerdb/powerdb/repositories/result_repository.py) `query_for_comparison()`（用了 `.mappings()` + `dict(m)`）。

### `session.execute(stmt, [dict, dict, ...])` ← 批量写
- **做什么**：**executemany** 批量插入，一条 SQL 携带多组参数，一次往返写入上千行。
- **原理**：对比逐条 `add`（N 次往返 N 条 SQL），批量写性能高一个量级，是时序数据的命门。
- **项目位置**：[repositories/timeseries_repository.py](../powerdb/powerdb/repositories/timeseries_repository.py) `bulk_insert_points()`。

### `session.delete(obj)` / `session.refresh(obj)` / `session.expire(obj)`
- `delete`：标记删除，flush 时发 DELETE。
- `refresh`：**重新从库加载**该对象，覆盖本地改动。
- `expire`：把属性标为过期，下次访问重新查（一般不用手动调）。

---

## 3. 查询构建层（Select / where / join / func）

> 这些方法是**纯 Python 表达式**，不碰数据库；只有交给 `session.execute/scalars/...` 才真正执行。

### `select(...)`
- `select(Model)`：查整张表返回实体。
- `select(Model.a, Model.b, ...)`：只查指定列，配 `.mappings()` 得到 dict。
- **排查点**：`select(Model)` 配 `.scalars()`、`select(多列)` 配 `.mappings()`，别配错。

### `.where(表达式)` vs `.filter_by(col=值)`
- `where`：任意 SQL 表达式，如 `where(Measurement.metric == "efficiency")`（`==` 会变成 SQL 的 `=`）。
- `filter_by`：关键字快捷方式，**只能做等值过滤**。
- **项目位置**：[repositories/base.py](../powerdb/powerdb/repositories/base.py) `get_by()`（filter_by）、[repositories/result_repository.py](../powerdb/powerdb/repositories/result_repository.py)（where）。

### `.join(表, 条件)` / `.outerjoin(...)`
- **做什么**：生成 `JOIN` / `LEFT JOIN`。
- **原理**：条件写成 `A.fk == B.id` 这种列等值。
- **项目位置**：[repositories/result_repository.py](../powerdb/powerdb/repositories/result_repository.py) 连续 JOIN 四张表取横向对比视图。

### `.order_by(col)` / `.limit(n)` / `.offset(n)`
- 排序 / 限制行数 / 跳过前 n 行。`order_by(col.desc())` 升序默认，`.desc()` 降序。

### `.label("别名")`
- **做什么**：给选中的列起别名，导出 dict 时用别名做 key。
- **项目位置**：[repositories/result_repository.py](../powerdb/powerdb/repositories/result_repository.py) `Sample.code.label("sample_code")`。

### `select_from(...)`
- **做什么**：聚合查询里显式指定 FROM 表。
- **项目位置**：[repositories/base.py](../powerdb/powerdb/repositories/base.py) `select(func.count()).select_from(self.model)`。

### `func.count() / avg() / sum() / min() / max()`
- **做什么**：SQL 聚合函数对象，只在 `select()` 内使用。
- **项目位置**：[repositories/base.py](../powerdb/powerdb/repositories/base.py) `count()`、`maintenance.py`。

---

## 4. 写操作（Core insert vs ORM add）

| 场景 | 写法 | 特点 |
| --- | --- | --- |
| 单条 / 少量 | `session.add(obj)` 或 `session.add_all(...)` | 生成 ORM 对象，回填 id，最直观 |
| 大批量（时序） | `session.execute(insert(Model), rows)` | executemany，一次往返，快 |
| 先插父拿 id | `add` + `flush()` | flush 回填 id 后可继续插子表 |

- **项目位置**：[repositories/timeseries_repository.py](../powerdb/powerdb/repositories/timeseries_repository.py) `bulk_insert_points()`（批量）、[api/app.py](../powerdb/powerdb/api/app.py)（add+flush）。

---

## 5. ORM 映射层（定义模型时用的方法）

### `DeclarativeBase`
- **原理**：声明式基类，所有模型继承它；`Base.metadata` 汇总全部表定义，供建表/Alembic 使用。
- **项目位置**：[core/base.py](../powerdb/powerdb/core/base.py)。

### `Mapped[类型]` + `mapped_column(...)`（SQLAlchemy 2.0 风格）
- **原理**：类型化列定义，让 IDE/类型检查更友好；`mapped_column` 里可加 `primary_key=True`、`String(64)`、`nullable=False`、`unique=True`、`index=True`。
- **项目位置**：[models/test_run.py](../powerdb/powerdb/models/test_run.py)。

### `ForeignKey("表.列")`
- **原理**：声明外键；`index=True` 顺便建索引（关联查询走索引更快）。
- **排查点**：SQLite 外键默认不生效，靠前面 `PRAGMA foreign_keys=ON` 打开。

### `relationship(back_populates=..., cascade="all, delete-orphan", lazy="select")`
- **做什么**：定义对象之间的关系，`back_populates` 双向关联、属性名对号。
- **`cascade="all, delete-orphan"`**：删除父对象时**级联删除子对象**，避免留下孤儿行或外键报错。
- **lazy 默认 `select`**：访问关系时**才**发 SQL 加载（惰性）。
- **⚠️ N+1 排查**：在循环里访问 `parent.children`，会触发「1 次取父 + N 次取子」= N+1 查询。解决：查询时预加载 `.options(selectinload(Parent.children))` 或 `joinedload(...)`。
- **⚠️ DetachedInstanceError**：session 关闭后再访问 `parent.children` 会报错，因为无法再惰性加载。
- **项目位置**：[models/test_run.py](../powerdb/powerdb/models/test_run.py) 的 `records`/`measurements`/`files` 等。

### `JSON().with_variant(JSONB(), "postgresql")`
- **原理**：跨方言类型——SQLite 落成 TEXT，PostgreSQL 自动用 JSONB。业务里统一写 `JSONType`，换库不感知。
- **项目位置**：[models/common.py](../powerdb/powerdb/models/common.py) `JSONType`。

### `server_default=func.now()` / `onupdate=func.now()`
- **原理**：前者=数据库端的默认值（插入时由 DB 填时间），后者=更新该行时自动更新时间。
- **项目位置**：[models/common.py](../powerdb/powerdb/models/common.py) `TimestampMixin`。

---

## 6. 排查清单（按现象 → 原因 → 定位）

| 现象/报错 | 常见原因 | 定位方法 |
| --- | --- | --- |
| `no such table` / `relation ... does not exist` | 没建表 | 运行 `create_schema()` 或跑 Alembic 迁移 |
| 插入了但下次查不到 | 忘了 `commit` | 用 `session_scope` 统一收口 |
| `MultipleResultsFound` | `scalar()`/`one()` 命中了多行 | 加主键/唯一条件，或改 `.first()` |
| `DetachedInstanceError` | session 已 close，又访问关系属性 | 在 session 内取值完毕；或提前 `selectinload` |
| N+1 / 查询特别慢 | 循环里访问 relationship | `.options(selectinload(...))` 预加载 |
| commit 后属性变 None / 多出 SELECT | `expire_on_commit=True`（默认） | 项目已设 `False`，别改回 |
| 删父表报外键错误 | 子表有引用、无级联 | 关系设 `cascade="all, delete-orphan"` |
| SQLite 外键不生效 | 没开 PRAGMA | 检查 `event.listens_for` 的 `PRAGMA foreign_keys=ON` |
| 中文字段写入乱码/None | 列类型或长度不符 | 打印 SQL，核对绑定参数与列类型 |
| 批量写入极慢 | 逐条 `add` | 改 `executemany`（`execute(insert, rows)`） |

---

## 7. 官方文档链接

- 引擎配置（create_engine / 连接池）：https://docs.sqlalchemy.org/en/20/core/engines.html
- Session 基础（状态/commit/flush）：https://docs.sqlalchemy.org/en/20/orm/session_basics.html
- 查询构建（select/where/join）：https://docs.sqlalchemy.org/en/20/orm/queryguide/select.html
- 关系（relationship/cascade/lazy）：https://docs.sqlalchemy.org/en/20/orm/relationship_api.html
- 类型系统（String/JSON/with_variant）：https://docs.sqlalchemy.org/en/20/core/type_basics.html
- Core INSERT/UPDATE/DELETE：https://docs.sqlalchemy.org/en/20/core/dml.html

---

## 8. 学习笔记

### 日常踩坑记录（Pitfalls）
| 日期 | 现象/问题 | 原因 | 解决/结论 |
| --- | --- | --- | --- |
|  |  |  |  |
|  |  |  |  |

### 学习待办（Todo）
- [ ] 开 `echo=True` 跑一遍 `seed_demo.py`，逐条读懂生成的 SQL
- [ ] 实验：`add` 后不 `commit`，看能否在此会话查到（理解 flush vs commit）
- [ ] 实验：session 关闭后访问 `parent.children`，复现 `DetachedInstanceError`
- [ ] 用手工构造的 N 条数据对比「逐条 add」与「executemany」的耗时