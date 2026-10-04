"""内部云的运维能力：健康检查、统计、备份。

对应「维护」这一环。内网 Windows PC 长期当归档服务器，最基本的三件事：
    1. 健康检查（库还通吗、存档盘还够吗）；
    2. 统计（库里现在有多少资产）；
    3. 备份（出事能恢复）。

备份策略：
    - SQLite：用 sqlite3 自带的 backup API（即使开了 WAL 也一致、安全），生成 .bak；
    - PostgreSQL：生产建议用 pg_dump 挂到 Windows 计划任务，此处只留提示，不硬编码命令。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select

from powerdb.core.engine import get_engine, session_scope
from powerdb.models.data_file import DataFile
from powerdb.models.project import Project, Sample
from powerdb.models.result import Measurement
from powerdb.models.standard import Standard, StandardItem
from powerdb.models.test_run import TestRecord, TestRun


def stats() -> dict:
    """各表行数，一眼看清库里有多少资产。"""
    with session_scope() as session:
        return {
            "projects": session.scalar(select(func.count()).select_from(Project)) or 0,
            "samples": session.scalar(select(func.count()).select_from(Sample)) or 0,
            "standards": session.scalar(select(func.count()).select_from(Standard)) or 0,
            "standard_items": session.scalar(select(func.count()).select_from(StandardItem)) or 0,
            "test_runs": session.scalar(select(func.count()).select_from(TestRun)) or 0,
            "test_records": session.scalar(select(func.count()).select_from(TestRecord)) or 0,
            "measurements": session.scalar(select(func.count()).select_from(Measurement)) or 0,
            "data_files": session.scalar(select(func.count()).select_from(DataFile)) or 0,
        }


def health(archive_dir: Path) -> dict:
    """健康检查：库文件大小 + 存档目录占用 + 文件数。"""
    db_path = _sqlite_path()
    db_size = db_path.stat().st_size if db_path and db_path.exists() else 0

    files = 0
    total = 0
    if archive_dir.exists():
        entries = [p for p in archive_dir.rglob("*") if p.is_file()]
        files = len(entries)
        total = sum(p.stat().st_size for p in entries)

    return {
        "ok": True,
        "db_size_bytes": db_size,
        "archive_dir": str(archive_dir),
        "archive_files": files,
        "archive_bytes": total,
    }


def backup(dest_dir: str | Path) -> Path:
    """SQLite 在线备份，生成 dest_dir/powerdb-<时间戳>.bak，返回备份路径。"""
    engine = get_engine()
    if not engine.url.drivername.startswith("sqlite"):
        raise NotImplementedError(
            "PostgreSQL 请用 pg_dump 挂到 Windows 计划任务（见 docs/12 维护章节），"
            "此处只实现了 SQLite 在线备份。"
        )
    src = engine.url.database  # sqlite 连接串里的文件路径
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"powerdb-{datetime.now().strftime('%Y%m%d-%H%M%S')}.bak"

    src_conn = sqlite3.connect(src)
    try:
        dst_conn = sqlite3.connect(dest)
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()
    return dest


def _sqlite_path() -> Path | None:
    engine = get_engine()
    if engine.url.drivername.startswith("sqlite"):
        return Path(engine.url.database)
    return None