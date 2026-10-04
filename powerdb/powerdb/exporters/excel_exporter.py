"""Excel 导出层：把业务视图行写成 .xlsx，交给非技术业务人员。

设计原则：
    - 用 openpyxl 直接拼表，控制表头加粗 / 列宽自适应 / 冻结首行，让业务「一目了然」；
    - 表头与列顺序来自 exporters/field_map.py 的 CASE_RECORD_FIELDS，改映射表即改导出，
      不写死任何列名，保证「表格设计」与「数据库设计」同源。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

from powerdb.exporters.field_map import CASE_RECORD_FIELDS

# 执行结果 -> 中文展示，硬件工程师无需记忆 pass/fail
_STATUS_TEXT = {
    "pass": "通过",
    "fail": "失败",
    "pending": "待执行",
}


def _fmt_datetime(value) -> str:
    if value is None:
        return ""
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _fmt_status(value) -> str:
    if value is None:
        return ""
    return _STATUS_TEXT.get(value, value)


def export_case_records(
    rows: Sequence[dict],
    path: str | Path,
    *,
    sheet_name: str = "用例执行记录",
) -> Path:
    """把用例执行记录行（来自仓储）写成 Excel，返回文件路径。"""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name

    headers = [f.header for f in CASE_RECORD_FIELDS]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for row in rows:
        values = []
        for f in CASE_RECORD_FIELDS:
            value = row.get(f.key, "")
            if f.key == "started_at":
                value = _fmt_datetime(value)
            elif f.key == "status":
                value = _fmt_status(value)
            elif value is None:
                value = ""
            values.append(value)
        ws.append(values)

    _autofit(ws)
    ws.freeze_panes = "A2"  # 冻结首行，滚动时表头常驻

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def export_case_records_to_excel(
    path: str | Path,
    *,
    run_no: Optional[str] = None,
    sample_code: Optional[str] = None,
    status: Optional[str] = None,
    sheet_name: str = "用例执行记录",
) -> Path:
    """从数据库查询用例执行记录并导出为 Excel（单入口）。

    内部：开事务 -> 仓储查业务视图 -> export_case_records 写表。
    """
    from powerdb.core.engine import session_scope
    from powerdb.repositories.export_repository import ExportRepository

    with session_scope() as session:
        rows = ExportRepository(session).query_case_records(
            run_no=run_no, sample_code=sample_code, status=status
        )
    return export_case_records(rows, path, sheet_name=sheet_name)


def export_judge_table(
    rows: Sequence[dict],
    path: str | Path,
    *,
    sheet_name: str = "判定结果",
) -> Path:
    """把判定结果（judge_metric 的输出）写成 Excel，不合格行标红、合格行标绿。

    表头与顺序来自 field_map.JUDGE_FIELDS，与业务列名同源。
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    from powerdb.exporters.field_map import JUDGE_FIELDS

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name

    headers = [f.header for f in JUDGE_FIELDS]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    red_fill = PatternFill("solid", fgColor="FFC7CE")    # 不合格：浅红
    green_fill = PatternFill("solid", fgColor="C6EFCE")  # 合格：浅绿

    for row in rows:
        values = []
        for f in JUDGE_FIELDS:
            value = row.get(f.key, "")
            values.append("" if value is None else value)
        ws.append(values)

        verdict = row.get("verdict")
        fill = red_fill if verdict == "不合格" else green_fill if verdict == "合格" else None
        if fill is not None:
            ws.cell(row=ws.max_row, column=len(headers)).fill = fill

    _autofit(ws)
    ws.freeze_panes = "A2"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def _autofit(ws, max_width: int = 40) -> None:
    """按内容最长视觉宽度设置列宽（中文按 2 个字符宽计）。"""
    from openpyxl.utils import get_column_letter

    for col_idx in range(1, ws.max_column + 1):
        letter = get_column_letter(col_idx)
        width = 0
        for cell in ws[letter]:
            if cell.value is None:
                continue
            char_width = sum(2 if ord(ch) > 127 else 1 for ch in str(cell.value))
            width = max(width, char_width)
        ws.column_dimensions[letter].width = min(width + 2, max_width)