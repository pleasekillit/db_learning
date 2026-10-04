"""端到端完整案例：从业务需求 -> 数据库设计 -> 代码实现 -> Excel 导出。

业务需求（真实储能逆变器送审场景）：
    型号 PCS-100 依据国标 GB/T 34120 送审，三个指标有硬性限值：
        额定效率  efficiency  >= 95%
        总谐波失真 thd         <= 5%
        温升        temp_rise   <= 60 ℃
    现有 3 台样机、多批次实测数据，需自动判定哪些批次不合格，并给评审一份 Excel 报告。

本脚本按四步走通全流程，并打印每步落在哪一层、哪份代码。

运行方式（在项目根目录 /workspace/powerdb 下）：
    python examples/end_to_end_case.py
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from powerdb.core.engine import create_schema, init_engine, session_scope
from powerdb.exporters import export_case_records_to_excel, export_judge_table
from powerdb.models import (
    DataFile,
    Measurement,
    Project,
    Sample,
    Standard,
    StandardItem,
    TestRecord,
    TestRun,
)
from powerdb.services.comparison_service import judge_metric

# (run_no, sample_code, 日期, [(test_item_code, metric, value, status), ...])
# 故意让三类指标都各有一批不合格，便于演示判定：
#   efficiency 有 94.1（<95）、thd 有 5.6（>5）、temp_rise 有 62（>60）
RUNS = [
    ("R-001", "S-1001", "2026-07-16", [
        ("EFF", "efficiency", 96.2, "pass"),
        ("THD", "thd", 3.1, "pass"),
        ("TEMP", "temp_rise", 47.0, "pass"),
    ]),
    ("R-002", "S-1002", "2026-07-22", [
        ("EFF", "efficiency", 95.4, "pass"),
        ("THD", "thd", 3.8, "pass"),
    ]),
    ("R-003", "S-1003", "2026-08-01", [
        ("EFF", "efficiency", 94.1, "fail"),   # 低于下限
        ("THD", "thd", 4.2, "pass"),
        ("TEMP", "temp_rise", 58.0, "pass"),
    ]),
    ("R-004", "S-1001", "2026-08-10", [
        ("EFF", "efficiency", 96.0, "pass"),
        ("TEMP", "temp_rise", 62.0, "fail"),   # 高于上限
    ]),
    ("R-005", "S-1002", "2026-08-20", [
        ("EFF", "efficiency", 95.9, "pass"),
        ("THD", "thd", 5.6, "fail"),           # 高于上限
    ]),
    ("R-006", "S-1003", "2026-09-05", [
        ("EFF", "efficiency", 96.4, "pass"),
        ("THD", "thd", 2.9, "pass"),
        ("TEMP", "temp_rise", 51.0, "pass"),
    ]),
]

DB_DESIGN = """
  数据库设计（实体从业务语句里拆出来，一层对多一层）：
    projects      项目  1 ──< samples      样品
    standards     标准  1 ──< standard_items 测试项（带 limit_min / limit_max）
    samples       样品  1 ──< test_runs    试验批次
    test_runs     批次  1 ──< test_records 测试记录（一次测一个测试项，status 存 pass/fail）
    test_records  记录  1 ──< measurements  标量结果（metric 是数据不建列，指标可扩展）
                        1 ──< data_files    相关数据文件
    —— 判定逻辑不落表，落在 service 层 judge_metric()，由 limit_min/limit_max 现算。
"""


def seed():
    """第2步：建库 + 写入数据（表结构已在 models/ 里"声明"好了）。"""
    with session_scope() as s:
        project = Project(name="储能逆变器送审", description="型号 PCS-100 国标 GB/T 34120")
        s1 = Sample(code="S-1001", name="样机1", model="PCS-100", project=project)
        s2 = Sample(code="S-1002", name="样机2", model="PCS-100", project=project)
        s3 = Sample(code="S-1003", name="样机3", model="PCS-100", project=project)
        std = Standard(code="GB/T 34120", name="储能变流器技术规范", category="国标")
        eff = StandardItem(code="EFF", name="额定效率", unit="%", limit_min=95.0, limit_max=100.0, standard=std)
        thd = StandardItem(code="THD", name="总谐波失真", unit="%", limit_min=None, limit_max=5.0, standard=std)
        temp = StandardItem(code="TEMP", name="温升", unit="℃", limit_min=None, limit_max=60.0, standard=std)

        items = {"EFF": eff, "THD": thd, "TEMP": temp}
        samples = {"S-1001": s1, "S-1002": s2, "S-1003": s3}
        s.add_all([project, s1, s2, s3, std, eff, thd, temp])
        s.flush()  # 立即拿到样本/测试项的 id

        for run_no, sample_code, day, entries in RUNS:
            run = TestRun(sample_id=samples[sample_code].id, run_no=run_no,
                          operator="张三", started_at=datetime.fromisoformat(day))
            s.add(run)
            s.flush()
            for item_code, metric, value, status in entries:
                rec = TestRecord(test_run_id=run.id, standard_item_id=items[item_code].id, status=status)
                s.add(rec)
                s.flush()
                s.add(Measurement(test_record_id=rec.id, metric=metric, value=value, unit=items[item_code].unit))
                # 给第一条效率记录挂一个原始波形文件，演示「相关数据文件」导出
                if metric == "efficiency" and run_no == "R-001":
                    s.add(DataFile(test_record_id=rec.id, name="R-001_效率波形.parquet",
                                   path="/archive/R-001/efficiency.parquet", kind="raw"))

        return {"EFF": eff.id, "THD": thd.id, "TEMP": temp.id}


def step3_judge(item_ids: dict) -> dict:
    """第3步：代码实现 —— 调用 service 层判定每个指标。"""
    results = {}
    for metric, item_id in [("efficiency", item_ids["EFF"]),
                            ("thd", item_ids["THD"]),
                            ("temp_rise", item_ids["TEMP"])]:
        results[metric] = judge_metric(metric, standard_item_id=item_id)
    return results


def step4_export(results: dict) -> None:
    """第4步：Excel 导出 —— 判定结果表 + 用例执行记录表。"""
    all_rows = [row for rows in results.values() for row in rows]
    judge_path = export_judge_table(all_rows, "exports/11_判定结果.xlsx")
    record_path = export_case_records_to_excel("exports/11_用例执行记录.xlsx")
    print(f"  已生成判定表：  {judge_path}")
    print(f"  已生成执行记录：{record_path}")


def show_conclusion(results: dict) -> None:
    """给业务看的口头结论。"""
    print("\n  —— 评审结论（给业务的话）——")
    for metric, rows in results.items():
        fails = [r for r in rows if r["verdict"] == "不合格"]
        name = rows[0]["item_name"] if rows else metric
        if fails:
            detail = "、".join(f"{r['run_no']}({r['value']})" for r in fails)
            print(f"  · {name}：共 {len(rows)} 批，{len(fails)} 批不合格 -> {detail}")
        else:
            print(f"  · {name}：共 {len(rows)} 批，全部合格")


def main() -> None:
    print("=== 第1步：业务需求 ===")
    print("  型号 PCS-100 送审，效率≥95%、THD≤5%、温升≤60℃，自动判定并出评审报告。")
    print(DB_DESIGN)

    init_engine()
    create_schema(drop=True)          # 第2步：建库
    item_ids = seed()                 # 第2步：写入数据

    print("=== 第3步：代码实现（service 层判定） ===")
    results = step3_judge(item_ids)
    for metric, rows in results.items():
        for r in rows:
            print(f"  {r['run_no']} {r['item_name']:<6} {r['value']}{r['unit']} -> {r['verdict']}")

    print("\n=== 第4步：Excel 导出（业务交付） ===")
    step4_export(results)
    show_conclusion(results)


if __name__ == "__main__":
    main()