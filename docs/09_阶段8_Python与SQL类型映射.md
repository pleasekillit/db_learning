# 阶段 8 · Python 与 SQL 的类型映射（容器怎么落地）

> 你写 Python 时几乎不关心类型：`x = 97.2` 和 `x = "97.2"` 都能跑；
> 但 SQL 对列类型要求严格，`REAL` 列不是 `TEXT` 列。更麻烦的是，Python 的特色容器
> `list / tuple / dict` 在关系表里**没有原生位置**。
>
> 本章回答三个工程问题：**谁来落地这层类型转换？容器怎么和 SQL 匹配？空值/布尔/时间这些坑怎么处理？**

## 本章目标
- 建立「Python 类型 ↔ SQLAlchemy 类型 ↔ SQL 存储」的映射直觉。
- 掌握三种容器降维策略：`dict` → JSON 列、`list/tuple` → 长表或 JSON 数组、`tuple` → 一行。
- 明白「类型强制」应落在哪两层：SQLAlchemy 列类型（存储层）+ Pydantic（边界层）。
- 会用往返验证，确认「写入的 Python 类型 = 读回的 Python 类型」。

## 对应代码位置

| 内容 | 对应代码 |
| --- | --- |
| 通用 JSON 类型（dict/list 进 JSON 列） | `powerdb/models/common.py` 的 `JSONType` |
| 各表字段的列类型声明 | `powerdb/models/*.py` 里每个 `mapped_column(String/Float/...)` |
| 时序长表（list/tuple → 一对多子表） | `powerdb/models/timeseries.py` 的 `TimeSeriesPoint` |
| 边界校验/强转（Pydantic） | `powerdb/schemas/result_schema.py` 的 `MeasurementCreate` |
| 往返对照演示 | `examples/type_mapping_demo.py` |
| 断言测试 | `tests/test_type_mapping.py` |

## 基础知识详解

### 1. 谁来做类型转换：两道闸

Python 代码「不写类型」的代价，是在**两个关键位置**要有人替你把关：

```
[仪器返回值/文件/HTTP] --① Pydantic 边界校验--> [Python 对象] --② SQLAlchemy 列类型--> [SQL 列]
```

- **② SQLAlchemy 列类型（自动、隐式）**：`mapped_column(Float)` 决定了这一列存浮点。
  你写入 `97.2` → 存 REAL；读回 → Python `float`。你几乎无需手写转换，因为类型已经声明在模型里。
- **① Pydantic 边界校验（主动、显式）**：仪器/文件/接口传来的可能是字符串 `"97.2"`、`None`、甚至 `"abc"`。
  这是「外部不信任数据」，必须在进库前用 Pydantic 强转或拒绝，否则脏数据带病入库。

> 结论：**库里不在写代码时纠结类型，而是提前把类型"声明"在模型列上、把"校验"放在边界上。**

### 2. 标量类型映射表（背下主干即可）

| Python 类型 | SQLAlchemy 列类型 | SQLite 落库 | PostgreSQL 落库 | 读回 Python | 备注 |
| --- | --- | --- | --- | --- | --- |
| `int` | `Integer` | INTEGER | INTEGER | `int` | 主键/外键 |
| `float` | `Float` | REAL | DOUBLE PRECISION | `float` | 精度敏感改用 `Numeric` |
| `Decimal` | `Numeric` | NUMERIC | NUMERIC | `Decimal` | 金额/高精度 |
| `str`(短) | `String(n)` | TEXT | VARCHAR(n) | `str` | 编号/代码 |
| `str`(长) | `Text` | TEXT | TEXT | `str` | 备注/日志 |
| `bool` | `Boolean` | INTEGER 0/1 | BOOLEAN | `bool` | 自动 0/1↔True/False |
| `datetime` | `DateTime` | TEXT(ISO) | TIMESTAMP | `datetime` | 时区看 `timezone=` |
| `date` | `Date` | TEXT | DATE | `date` | |
| `bytes` | `LargeBinary` | BLOB | BYTEA | `bytes` | 二进制文件 |
| `None` | 任意可空列 | NULL | NULL | `None` | 受 `nullable` 控制 |

### 3. 容器降维策略（重点）

关系表只有「标量、行、表」三种形态，没有 `list/tuple/dict/set`，所以必须**降维**：

| Python 容器 | 推荐落地 | 适用场景 | 骨架里的例子 |
| --- | --- | --- | --- |
| `dict` | **JSON 列** | 结构随意、不按内部字段聚合的元数据 | `TestRun.environment`、`Measurement.extra`、`Instrument.connection` |
| `list/tuple`（标量）需聚合 | **长表**（一对多子表） | 逐点查询/聚合/范围 | `TimeSeriesPoint(channel_id, t, value)` |
| `list`（标量）只读一坨 | **JSON 数组列** | 归档整存、不逐元素查 | `environment` 里塞 `{"seq": [1,2,3]}` |
| `tuple` 表示「一行」 | **拆成列** | `(t, value)` → 两列 | `TimeSeriesPoint(t, value)` |
| `dict` 嵌套文档 | **JSON 列**（文档型） | 快照/整份配置 | 仪器 `connection` |

**判据**（决定拆表还是塞 JSON）：**要不要按它内部字段做 SQL 过滤/聚合？**
- 要（如"查某时间窗内所有采样点"）→ 拆**长表**；
- 不要（如"这串只是环境温湿度备注"）→ 存 **JSON 列**。

### 4. JSON 列怎么在 SQLite/PG 间自适应

`common.py` 里：
```python
JSONType = JSON().with_variant(JSONB(), "postgresql")
```
- SQLite 下 `JSON()` 落成 TEXT（本质是 `json.dumps` 后的字符串）；
- PostgreSQL 下自动换成 `JSONB`（可建 GIN 索引，可按内部字段查询）。
- 业务代码统一写 `JSONType`，换库不感知方言差异——这就是「类型映射」在换库时也不用手改的价值。

### 5. dict 进 JSON 列的写入/读回（含 bool/list 保真）

```python
run = TestRun(environment={"temp_c": 25.0, "rh": 45, "passed": True, "seq": [1, 2, 3]})
session.add(run)
# 读回：
run.environment["passed"]  # -> True（bool 不变）
run.environment["seq"]     # -> [1, 2, 3]（list 不变）
```
SQLAlchemy 的 `JSON` 类型在写入时 `json.dumps`、读回时 `json.loads`，所以 Python 的
`bool/list/dict/number/str` 在 JSON 列内**保真往返**。

### 6. list/tuple 进长表（时序点是典型）

```python
# 一条通道下的采样点：list[tuple[float, float]] -> 长表 TimeSeriesPoint
data = [(0.0, 10.0), (0.001, 10.1), (0.002, 10.2)]
create_channel(record_id, "Ia", unit="A", data=data)
```
每个 `(t, value)` 是一行：`t` 进 `Float` 列、`value` 进 `Float` 列。写入时是 tuple，
落库变成两列标量，读回又是 `[(t, value), ...]`——容器通过"拆行"完成了与 SQL 的匹配。

### 7. Pydantic 边界强转（系统入口那一下）

```python
MeasurementCreate(value="97.2")   # str -> float 强转成功，value == 97.2
MeasurementCreate(value="abc")     # 抛 ValidationError，拒绝入内
```
仪器返回的字符串、CSV 读出来的字符串，都在这一层被规范成 `.value: Optional[float]` 声明的类型。

## 训练 Demo 详解

**准备**（项目根目录 `/workspace/powerdb` 下）：
```bash
python examples/type_mapping_demo.py
```
输出会逐段打印「写入的 Python 类型 → 读回的 Python 类型」，覆盖：
1. 标量往返（str/float/datetime/None）；
2. dict（含 bool/list）进 JSON 列的保真；
3. list[tuple] 进长表的拆行；
4. Pydantic 的强转与拒绝。

**任务**：改一下 `environment` 里的值（换成你的仪器环境字段），重跑确认类型不丢。

**进阶验证**：`python -m pytest tests/test_type_mapping.py -q`，用断言把「往返一致」钉死成回归测试。

## 官方文档链接
- SQLAlchemy 列类型与 Python 类型对照：https://docs.sqlalchemy.org/en/20/core/type_basics.html
- SQLAlchemy JSON 类型：https://docs.sqlalchemy.org/en/20/core/type_basics.html#sqlalchemy.types.JSON
- Pydantic 类型强转（coercion）：https://docs.pydantic.dev/latest/concepts/conversion_table/

## 学习笔记

### 日常踩坑记录（Pitfalls）
| 日期 | 现象/问题 | 原因 | 解决/结论 |
| --- | --- | --- | --- |
| 示例 | 把 dict 直接塞 String 列报类型错误 | 列类型与 Python 对象不匹配 | dict 走 `JSONType`，标量才走 String/Float 等 |
| 示例 | bool 读回变成 0/1 | 用了 Integer 列存布尔 | 用 `Boolean`，SQLAlchemy 自动转 True/False |
| 示例 | float 存金额出现 0.1+0.2 精度漂移 | REAL 二进制浮点 | 精度场景用 `Numeric` 或存整数+单位 |
| 示例 | 时区丢了/报错 | naive vs aware datetime | 用 `DateTime(timezone=True)` 统一 UTC |
|  |  |  |  |

### 学习待办（Todo）
- [ ] 跑 `type_mapping_demo.py`，对照打印确认「写入=读回」
- [ ] 挑一个自己业务里的 dict，决定它该进 JSON 列还是拆表，并写理由
- [ ] 给一个 CSV 读取入口加 Pydantic 强转，验证非法值被拒