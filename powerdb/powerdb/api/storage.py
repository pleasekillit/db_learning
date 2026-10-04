"""归档文件存储层。

「归档」= 把原始波形 / 报告 / 日志落到内部云的文件区（一个网络共享目录），
同时在 data_files 表登记一条记录，让「文件」与「数据库」不脱节：
    - name：给业务看的文件名（导出到 Excel 的「相关数据文件」列）；
    - path：实际存储位置（给程序回查 / 下载用）；
    - kind：raw / report / log / image，便于分类归档。

目录约定：<归档根>/<run_no>/<文件名>。
归档根可通过环境变量 POWERDB_ARCHIVE_DIR 指定，默认项目根下的 archive/。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from powerdb.models.data_file import DataFile


def archive_root() -> Path:
    return Path(
        os.environ.get(
            "POWERDB_ARCHIVE_DIR",
            str(Path(__file__).resolve().parent.parent.parent / "archive"),
        )
    )


def store_file(
    *,
    run_no: str,
    filename: str,
    content: bytes,
    session: Session,
    test_record_id: int,
    kind: str,
    note: Optional[str] = None,
) -> DataFile:
    """把文件字节写进归档目录，并在 data_files 登记。返回该 DataFile（未 commit）。"""
    target = archive_root() / run_no
    target.mkdir(parents=True, exist_ok=True)
    path = target / filename
    # 同名覆盖的取舍：归档要求不覆盖历史；生产里可在此加「时间戳/序号」防冲突。
    path.write_bytes(content)

    df = DataFile(
        test_record_id=test_record_id,
        name=filename,
        path=str(path),
        kind=kind,
        note=note,
    )
    session.add(df)
    return df