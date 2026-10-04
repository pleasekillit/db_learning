"""价值演示：用「业务问题 -> 一条查询 -> 秒级答案」证明数据库的价值。

给谁的：电力电子硬件工程师（不关心表/键/范式，只关心「我要的结论你多久给我」）。

怎么演：先问一句「没数据库时，下面这三个问题你平时怎么查？要多久？」，再当场跑本脚本，
        把「现在 vs 以前」的对比摆在他们面前。

运行方式（在项目根目录 /workspace/powerdb 下）：
    python examples/value_demo.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func, select

from powerdb.core.engine import create_schema, init_engine, session_scope
from powerdb.exporters import export_case_records_to_excel
from powerdb.models import (
    Measurement,
    Project,
    Sample,
    Standard,
    StandardItem,
    TestRecord,
    TestRun,
)
from powerdb.services.comparison_service import compare_metric


# 演示数据：两个同型号样品、跨两个月、若干批次，含 2 次效率超限（失败）。
# (run_no, sample_code, 日期, [(item_code, metric, value, unit, status), ...])
RUNS = [
    ("RUN-001", "S-0001", "2026-07-20", [
        ("EFF", "efficiency", 96.5, "%", "pass"),
        ("THD", "thd", 3.2, "%", "pass"),
        ("TEMP", "temp_rise", 48.0, "℃", "pass"),
    ]),
    ("RUN-002", "S-0002", "2026-07-25", [
        ("EFF", "efficiency", 96.1, "%", "pass"),
    ]),
    ("RUN-003", "S-0001", "2026-08-05", [
        ("EFF", "efficiency", 94.2, "%", "fail"),   # 低于下限 95
        ("THD", "thd", 4.1, "%", "pass"),
    ]),
    ("RUN-004", "S-0002", "2026-08-18", [
        ("EFF", "efficiency", 95.8, "%", "pass"),
        ("TEMP", "temp_rise", 55.0, "℃", "pass"),
    ]),
    ("RUN-005", "S-0001", "2026-09-10", [
        ("EFF", "efficiency", 93.8, "%", "fail"),   # 低于下限 95
        ("THD", "thd", 4.9, "%", "pass"),
    ]),
    ("RUN-006", "S-0002", "2026-09-20", [
        ("EFF", "efficiency", 96.0, "%", "pass"),
    ]),
]


def seed() -> None:
    """把演示数据写入数据库。"""
    with session_scope() as s:
        project = Project(name="储能逆变器")
        sa = Sample(code="S-0001", name="样品A", model="PCS-100", project=project)
        sb = Sample(code="S-0002", name="样品B", model="PCS-100", project=project)
        std = Standard(code="GB/T 34120", name="储能逆变器标准", category="国标")
        item_eff = StandardItem(code="EFF", name="额定效率", unit="%", limit_min=95.0, limit_max=100.0, standard=std)
        item_thd = StandardItem(code="THD", name="总谐波", unit="%", limit_max=5.0, standard=std)
        item_temp = StandardItem(code="TEMP", name="温升", unit="℃", limit_max=60.0, standard=std)
        items = {"EFF": item_eff, "THD": item_thd, "TEMP": item_temp}
        samples = {"S-0001": sa, "S-0002": sb}

        s.add_all([project, sa, sb, std, item_eff, item_thd, item_temp])
        s.flush()  # 立即拿到 sa.id / sb.id / item.id

        for run_no, sample_code, day, entries in RUNS:
            run = TestRun(sample_id=samples[sample_code].id, run_no=run_no, operator="演示")
            s.add(run)
            s.flush()
            for item_code, metric, value, unit, status in entries:
                rec = TestRecord(
                    test_run_id=run.id,
                    standard_item_id=items[item_code].id,
                    status=status,
                )
                s.add(rec)
                s.flush()
                s.add(Measurement(test_record_id=rec.id, metric=metric, value=value, unit=unit))


def q1_efficiency_trend() -> None:
    """业务问题 1：这个型号所有批次的效率，历史趋势 + 均值 + 谁超限了？"""
    print("=" * 60)
    print("问题1：PCS-100 各批次额定效率趋势？均值多少？哪几批低于 95% 下限？")
    t0 = time.perf_counter()
    rows = compare_metric("efficiency")
    values = [r["value"] for r in rows if r["value"] is not None]
    mean = sum(values) / len(values)
    below = [r for r in rows if r["value"] is not None and r["value"] < 95.0]
    elapsed = (time.perf_counter() - t0) * 1000

    for r in rows:
        flag = "  <-- 超限" if r in below else ""
        print(f"  {r['run_no']}  {r['sample_code']}  {r['value']}{r['unit']}{flag}")
    print(f"  均值 = {mean:.2f}%，最低 {min(values)}%，共 {len(values)} 批")
    print(f"  >>> 一条查询 {elapsed:.1f} ms 出结果。")
    print("  没数据库时：翻 6 个文件、手动把效率列复制到一张表、排序求均值、肉眼找超限，约 30 分钟+。\n")


def q2_pass_rate() -> None:
    """业务问题 2：整体通过率多少？哪个测试项失败最多？"""
    print("=" * 60)
    print("问题2：最近这批整体通过率？哪个测试项最容易失败？")
    with session_scope() as s:
        total = s.scalar(select(func.count()).select_from(TestRecord))
        failed = s.scalar(select(func.count()).select_from(TestRecord).where(TestRecord.status == "fail"))
        fail_by_item = s.execute(
            select(StandardItem.name, func.count())
            .join(TestRecord, TestRecord.standard_item_id == StandardItem.id)
            .where(TestRecord.status == "fail")
            .group_by(StandardItem.name)
            .order_by(func.count().desc())
        ).all()

    passed = total - failed
    print(f"  用例记录 {total} 条：通过 {passed}，失败 {failed}，通过率 {passed / total * 100:.1f}%")
    for name, cnt in fail_by_item:
        print(f"  失败最多：{name}，失败 {cnt} 次")
    print("  没数据库时：逐个打开报告数 pass/fail 再汇总，跨几十个文件时几乎不可行。\n")


def q3_excel_delivery() -> None:
    """业务问题 3：把用例执行记录 + 相关数据文件导出成 Excel 给我。"""
    print("=" * 60)
    print("问题3：把这次所有用例执行记录导成一个 Excel 给我。")
    out = export_case_records_to_excel("exports/价值演示_用例执行记录.xlsx")
    print(f"  已生成：{out}")
    print("  打开就是中文表头：用例编号 / 用例名称 / 样品 / 试验 / 执行时间 / 结果 / 相关数据文件。\n")


ROI_NOTES = [
    ("省时间", "季度汇总报告：人工合并 N 个 Excel 要 1~2 人天，数据库一条查询秒回，0 人天。"),
    ("省硬件", "同型号历史数据可直接复用做横向对比，新项目少做几轮重复测试，少占台架、少烧器件。"),
    ("少出错", "每笔数据带时间戳/操作员/状态，出问题可追溯；Excel 版本身版本混乱、易被覆盖改坏。"),
    ("数据资产", "项目结束 Excel 就散落丢失；数据库让数据变成团队资产，人来人走数据都在。"),
    ("为 AI 铺路", "结构化、可切片的历史数据，是后续 AI 故障诊断/寿命预测的前提，先攒数据后期才有戏。"),
]


def closing() -> None:
    print("=" * 60)
    print("用数据库的 5 个价值（向业务这样讲，别讲表/键/范式）：\n")
    for title, detail in ROI_NOTES:
        print(f"  · {title}：{detail}")
    print("\n  —— 记住一句话：你没问「怎么存」，我只回答「你的业务问题多快能得到答案」。")


def main() -> None:
    init_engine()
    create_schema(drop=True)
    seed()

    q1_efficiency_trend()
    q2_pass_rate()
    q3_excel_delivery()
    closing()


if __name__ == "__main__":
    main()