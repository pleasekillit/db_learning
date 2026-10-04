"""Excel 导出演示：建库 -> 写入用例执行记录（含相关数据文件）-> 导出 Excel。

运行方式（在项目根目录 /workspace/powerdb 下）：
    python examples/export_demo.py
"""
import os
import sys
from datetime import datetime

# 让脚本能 import 项目根目录下的 powerdb 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from powerdb.core.engine import create_schema, init_engine, session_scope
from powerdb.models import (
    DataFile,
    Project,
    Sample,
    Standard,
    StandardItem,
    TestRecord,
    TestRun,
)
from powerdb.exporters import export_case_records_to_excel


def main() -> None:
    init_engine()              # 使用默认配置（本地 SQLite）
    create_schema(drop=True)   # 演示：先重建干净库

    # 写入用例执行记录 + 相关数据文件（一个事务）
    with session_scope() as session:
        project = Project(name="储能逆变器")
        sample = Sample(code="S-0001", name="逆变器样品A", model="PCS-100", project=project)
        std = Standard(code="GB/T 34120", name="电化学储能系统逆变器标准", category="国标")
        item = StandardItem(
            code="EFF", name="额定效率", unit="%",
            limit_min=95.0, limit_max=100.0, standard=std,
        )
        session.add_all([project, sample, std, item])
        session.flush()

        run = TestRun(sample_id=sample.id, run_no="RUN-2026-001", operator="张三")
        session.add(run)
        session.flush()

        rec = TestRecord(
            test_run_id=run.id, standard_item_id=item.id,
            status="pass",
            started_at=datetime(2026, 9, 26, 10, 0, 0),
            finished_at=datetime(2026, 9, 26, 10, 15, 0),
        )
        session.add(rec)
        session.flush()

        # 「相关数据文件」：业务只关心文件名，路径另存，导出时只给 name
        session.add_all([
            DataFile(test_record_id=rec.id, name="EFF_原始波形.parquet",
                     path="/data/archive/RUN-2026-001/EFF_raw.parquet", kind="raw"),
            DataFile(test_record_id=rec.id, name="EFF_报告.pdf",
                     path="/data/archive/RUN-2026-001/EFF_report.pdf", kind="report"),
        ])

    out = export_case_records_to_excel("exports/用例执行记录.xlsx")
    print("已导出 Excel：", out)
    print("打开后即可看到：用例编号 / 用例名称 / 样品编号 / 试验编号 / "
          "执行时间 / 执行结果 / 相关数据文件。")


if __name__ == "__main__":
    main()