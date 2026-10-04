"""Python 类型 与 SQL 类型的落地对照演示。

回答三个工程问题：
1) Python 写着不关心类型，SQL 却对列类型要求严格 —— 谁来落地这层转换？
   答：两道闸。SQLAlchemy 列类型(存储层，自动) + Pydantic(边界层，主动强转/拒绝)。
2) Python 的 list / tuple / dict 在关系表里没有原生位置 —— 怎么和 SQL 匹配？
   答：容器必须"降维"：
      dict              -> JSON 列（JSONType）
      list[tuple] 需聚合 -> 长表（一对多，如 TimeSeriesPoint）
      list 只读一坨      -> JSON 数组（塞进 JSON 列）
      tuple 表示"一行"   -> 拆成一行多列
3) 空值 None、布尔、时间等"隐形坑" —— 怎么确认没丢？
   答：做"往返验证"：写入的 Python 类型 == 读回的 Python 类型。

运行方式（在项目根目录 /workspace/powerdb 下）：
    python examples/type_mapping_demo.py
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import ValidationError
from sqlalchemy import select

from powerdb.core.engine import create_schema, init_engine, session_scope
from powerdb.models import (
    Measurement,
    Project,
    Sample,
    Standard,
    StandardItem,
    TestRecord,
    TestRun,
)
from powerdb.schemas.result_schema import MeasurementCreate
from powerdb.services.timeseries_service import create_channel, read_channel


def _label(name: str, obj) -> None:
    """打印一段对照：名字 / 值 / Python 类型。"""
    print(f"{name:<26} value={obj!r:<22} type={type(obj).__name__}")


def scalar_and_dict_demo() -> None:
    print("== 1) 标量往返 + dict 进 JSON 列 ==")
    with session_scope() as s:
        project = Project(name="储能逆变器")
        sample = Sample(code="S-0001", name="样品A", project=project)  # str 列
        std = Standard(code="GB/T 34120", name="标准")                    # str 列
        item = StandardItem(code="EFF", name="额定效率", unit="%", standard=std)
        s.add_all([project, sample, std, item])
        s.flush()

        run = TestRun(
            sample_id=sample.id,
            run_no="RUN-2026-001",                                            # str 列
            environment={"temp_c": 25.0, "rh": 45, "passed": True, "seq": [1, 2, 3]},  # dict -> JSON 列
        )
        s.add(run)
        s.flush()

        rec = TestRecord(
            test_run_id=run.id,
            standard_item_id=item.id,
            status="pass",                                  # str 列
            started_at=datetime(2026, 9, 26, 10, 0, 0),     # datetime 列
        )
        s.add(rec)
        s.flush()
        s.add(Measurement(test_record_id=rec.id, metric="efficiency", value=97.2, unit="%"))  # float 列

        _run_id = run.id

    # 读回：验证「写入的 Python 类型 == 读回的 Python 类型」
    with session_scope() as s:
        run = s.get(TestRun, _run_id)
        env = run.environment
        print("  --- dict 进 JSON 列后读回 ---")
        _label("    environment", env)
        _label("    env['passed']", env["passed"])   # bool 保真
        _label("    env['seq']", env["seq"])         # list 保真

        m = s.scalar(select(Measurement).where(Measurement.metric == "efficiency"))
        _label("    m.value", m.value)               # float 保真


def list_tuple_long_table_demo(record_id: int) -> None:
    print("\n== 2) list[tuple] -> 长表(一对多) ==")
    # data 是 list[tuple[float, float]]：每个 tuple 是「一行」，被拆成 t、value 两列
    data = [(i / 1000.0, round(10.0 * (i % 3), 3)) for i in range(5)]
    channel_id = create_channel(record_id, "Ia", unit="A", sample_rate=1000.0, data=data)

    # 读回的是 [(t, value), ...]，每一行又回到 tuple
    points = read_channel(channel_id)
    for t, v in points:
        _label(f"    point ({t}, {v})", (t, v))
    print("    每行 (t, value) 都来自长表 TimeSeriesPoint 的两列标量。")


def pydantic_boundary_demo() -> None:
    print("\n== 3) Pydantic 边界强转 / 拒绝 ==")
    ok = MeasurementCreate(test_record_id=1, metric="efficiency", value="97.2")  # str -> float
    _label("    强转后 ok.value", ok.value)

    try:
        MeasurementCreate(test_record_id=1, metric="efficiency", value="abc")  # 无法转 float
    except ValidationError as exc:
        print("    非法入参被拒：", exc.errors()[0]["msg"][:40], "...")


def main() -> None:
    init_engine()              # 默认本地 SQLite
    create_schema(drop=True)   # 干净库起步

    # 1) 标量 + dict
    scalar_and_dict_demo()

    # 需要一条已提交的 TestRecord 才能建通道，这里单独造最小记录
    with session_scope() as s:
        p = Project(name="临时项目")
        sample = Sample(code="TMP-1", name="临时样品", project=p)
        std = Standard(code="TMP-GB", name="临时标准")
        item = StandardItem(code="TMP-EFF", name="临时项", unit="%", standard=std)
        s.add_all([p, sample, std, item])
        s.flush()
        run = TestRun(sample_id=sample.id, run_no="TMP-RUN")
        s.add(run)
        s.flush()
        rec = TestRecord(test_run_id=run.id, standard_item_id=item.id, status="pass")
        s.add(rec)
        s.flush()
        _record_id = rec.id

    # 2) list + tuple
    list_tuple_long_table_demo(_record_id)

    # 3) Pydantic
    pydantic_boundary_demo()

    print("\n结论：库里不写类型，而是把类型声明在 mapped_column、把校验放在 Pydantic 边界；"
          "容器靠「JSON 列 / 长表 / 拆行」三种方式降维。")


if __name__ == "__main__":
    main()