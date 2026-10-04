"""导出字段映射表：业务词汇 ↔ 数据库字段 ↔ Excel 列名。

这是「表格设计」与「数据库设计」不割裂的单一事实来源（single source of truth）：
    - 业务人员（电力电子硬件工程师）只认中文列名和业务词汇；
    - 数据库只认英文字段名；
    - 这张表把两边钉在一起，改列名 / 加列都只在这里改，导出结果与文档同步。

用法：导出层（excel_exporter）按这里的顺序生成 Excel 表头、按 key 取行数据，
因此「业务要几列、每列对应库里的哪个字段」只在这一处维护。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExportField:
    key: str          # 业务视图行的键（由仓储产出，与数据库字段一一对应）
    header: str       # Excel 表头中文名（给业务看）
    source: str       # 数据库来源说明（表.字段），业务/开发沟通用
    description: str  # 业务含义


# 用例执行记录导出的列定义：顺序即 Excel 列顺序。
# 覆盖业务最关心的 5 项：用例编号 / 用例名称 / 执行时间 / 执行结果 / 相关数据文件，
# 另加 样品编号 / 试验编号 作上下文，避免同一用例跑多次时无法区分。
CASE_RECORD_FIELDS: tuple[ExportField, ...] = (
    ExportField(
        key="case_code",
        header="用例编号",
        source="standard_items.code",
        description="对应标准里的测试项编号，如 EFF",
    ),
    ExportField(
        key="case_name",
        header="用例名称",
        source="standard_items.name",
        description="测试项名称，如 额定效率",
    ),
    ExportField(
        key="sample_code",
        header="样品编号",
        source="samples.code",
        description="被测样品编号，如 S-0001",
    ),
    ExportField(
        key="run_no",
        header="试验编号",
        source="test_runs.run_no",
        description="一次完整试验批次编号，如 RUN-2026-001",
    ),
    ExportField(
        key="started_at",
        header="执行时间",
        source="test_records.started_at",
        description="用例开始执行的时间",
    ),
    ExportField(
        key="status",
        header="执行结果",
        source="test_records.status",
        description="pass 通过 / fail 失败 / pending 待执行",
    ),
    ExportField(
        key="files",
        header="相关数据文件",
        source="data_files.name",
        description="关联的原始数据 / 报告 / 日志文件名（多个用 ; 分隔）",
    ),
)

# 若业务以后要加「测量值 / 单位」等列，在此追加 ExportField 即可，导出自适应。

# 判定结果导出的列定义：某个指标各批次对照标准限值的判定表。
JUDGE_FIELDS: tuple[ExportField, ...] = (
    ExportField("run_no", "试验编号", "test_runs.run_no", "试验批次编号"),
    ExportField("sample_code", "样品编号", "samples.code", "被测样品编号"),
    ExportField("item_name", "测试项", "standard_items.name", "标准测试项名称"),
    ExportField("value", "测量值", "measurements.value", "实测标量值"),
    ExportField("unit", "单位", "measurements.unit", "计量单位"),
    ExportField("limit_min", "下限", "standard_items.limit_min", "合格下限"),
    ExportField("limit_max", "上限", "standard_items.limit_max", "合格上限"),
    ExportField("verdict", "判定", "（计算得到）", "合格 / 不合格 / 未判"),
)