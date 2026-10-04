"""端到端演示：建库 -> 写入一次完整试验 -> 历史横向对比 -> 时序写入。

运行方式（在项目根目录 /workspace/powerdb 下）：
    python examples/seed_demo.py
"""
import os
import sys

# 让脚本能 import 项目根目录下的 powerdb 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from powerdb.core.engine import create_schema, init_engine, session_scope
from powerdb.models import (
    Instrument,
    Measurement,
    Project,
    Sample,
    Standard,
    StandardItem,
    TestRecord,
    TestRun,
)
from powerdb.services.comparison_service import compare_metric, summarize_metric
from powerdb.services.timeseries_service import create_channel


def main() -> None:
    init_engine()            # 使用默认配置（本地 SQLite）
    create_schema(drop=True)  # 演示：先重建干净库

    # 第一阶段：写入试验业务数据（一个事务）
    with session_scope() as session:
        project = Project(name="储能逆变器", description="示范项目")
        sample_a = Sample(code="S-0001", name="逆变器样品A", model="PCS-100", project=project)
        sample_b = Sample(code="S-0002", name="逆变器样品B", model="PCS-100", project=project)

        std = Standard(code="GB/T 34120", name="电化学储能系统逆变器标准", category="国标")
        item = StandardItem(
            code="EFF", name="额定效率", unit="%",
            limit_min=95.0, limit_max=100.0, standard=std,
        )
        instr = Instrument(name="功率分析仪", model="WT5000", connection={"port": "TCPIP::192.168.0.10"})

        session.add_all([project, sample_a, sample_b, std, item, instr])
        session.flush()

        # 样品 A 的一次试验
        run_a = TestRun(
            sample_id=sample_a.id, run_no="RUN-2026-001", operator="张三",
            environment={"temp_c": 25.0, "rh": 45.0},
        )
        session.add(run_a)
        session.flush()
        rec_a = TestRecord(
            test_run_id=run_a.id, standard_item_id=item.id,
            instrument_id=instr.id, status="pass",
        )
        session.add(rec_a)
        session.flush()
        session.add(Measurement(test_record_id=rec_a.id, metric="efficiency", value=97.2, unit="%"))

        # 样品 B 的一次试验（用于横向对比）
        run_b = TestRun(sample_id=sample_b.id, run_no="RUN-2026-002", operator="李四")
        session.add(run_b)
        session.flush()
        rec_b = TestRecord(
            test_run_id=run_b.id, standard_item_id=item.id,
            instrument_id=instr.id, status="pass",
        )
        session.add(rec_b)
        session.flush()
        session.add(Measurement(test_record_id=rec_b.id, metric="efficiency", value=96.1, unit="%"))

        record_a_id = rec_a.id

    # 第二阶段：写入一条时序通道（独立事务，演示 FK 已提交可用）
    channel_id = create_channel(
        record_a_id, "Ia_phase_current", unit="A", sample_rate=1000.0,
        data=[(i / 1000.0, 10.0 * (i % 3)) for i in range(1000)],
    )
    print(f"已写入时序通道 id={channel_id}, 点数=1000")

    # 历史横向对比
    print("\n横向对比 efficiency：")
    for row in compare_metric("efficiency"):
        print(f"  {row['sample_code']} / {row['run_no']} / {row['item_name']}: "
              f"{row['value']}{row['unit']}")

    print("\n概要统计：", summarize_metric("efficiency"))


if __name__ == "__main__":
    main()