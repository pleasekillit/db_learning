"""内部云服务：把 powerdb 的分层架构包成 REST 接口，供 3~10 人内网团队共用。

四大能力 → 接口：
    管理 manage  -> POST/GET /api/projects、/api/samples、/api/standards、/api/standard-items
    提交 submit  -> POST /api/runs（一次提交完整试验 + 记录 + 测量值）
    归档 archive -> POST /api/records/{id}/files（上传）、GET /api/records/{id}/files/{name}（下载）、GET /api/archive
    查询/导出    -> GET /api/comparison、/api/judge、/api/export/case-records
    维护 maintain-> GET /api/maintenance/health|stats、POST /api/maintenance/backup

运行（内网 Windows PC 上）：
    uvicorn powerdb.api.app:app --host 0.0.0.0 --port 8000
    （访问 http://<这台PC的内网IP>:8000/docs 可看交互式接口文档）
"""
from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from powerdb import maintenance
from powerdb.api.deps import get_session, require_intranet
from powerdb.api.schemas import (
    ProjectIn,
    RecordIn,
    RunIn,
    SampleIn,
    StandardIn,
    StandardItemIn,
)
from powerdb.api.storage import archive_root, store_file
from powerdb.core.engine import session_scope
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
from powerdb.services.comparison_service import compare_metric, judge_metric

app = FastAPI(
    title="PowerDB 内部云",
    description="电力电子测试数据的多人归档服务：管理 / 提交 / 归档 / 维护",
    version="0.1.0",
)

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _iso(value) -> str:
    return "" if value is None else value.strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------- 管理 manage

@app.post("/api/projects", status_code=201)
def create_project(payload: ProjectIn, session: Session = Depends(get_session)):
    obj = Project(name=payload.name, description=payload.description)
    session.add(obj)
    session.flush()
    return {"id": obj.id, "name": obj.name, "description": obj.description}


@app.get("/api/projects")
def list_projects(session: Session = Depends(get_session)):
    return [
        {"id": p.id, "name": p.name, "description": p.description}
        for p in session.scalars(select(Project).order_by(Project.id))
    ]


@app.post("/api/samples", status_code=201)
def create_sample(payload: SampleIn, session: Session = Depends(get_session)):
    if session.get(Project, payload.project_id) is None:
        raise HTTPException(404, "项目不存在")
    obj = Sample(
        project_id=payload.project_id,
        code=payload.code,
        name=payload.name,
        model=payload.model,
        spec_sn=payload.spec_sn,
        manufacturer=payload.manufacturer,
    )
    session.add(obj)
    session.flush()
    return {"id": obj.id, "code": obj.code, "name": obj.name, "model": obj.model}


@app.get("/api/samples")
def list_samples(project_id: int | None = None, session: Session = Depends(get_session)):
    stmt = select(Sample).order_by(Sample.id)
    if project_id is not None:
        stmt = stmt.where(Sample.project_id == project_id)
    return [
        {"id": s.id, "code": s.code, "name": s.name, "model": s.model, "project_id": s.project_id}
        for s in session.scalars(stmt)
    ]


@app.post("/api/standards", status_code=201)
def create_standard(payload: StandardIn, session: Session = Depends(get_session)):
    obj = Standard(code=payload.code, name=payload.name,
                   category=payload.category, version=payload.version)
    session.add(obj)
    session.flush()
    return {"id": obj.id, "code": obj.code, "name": obj.name}


@app.get("/api/standards")
def list_standards(session: Session = Depends(get_session)):
    return [
        {"id": s.id, "code": s.code, "name": s.name, "category": s.category}
        for s in session.scalars(select(Standard).order_by(Standard.id))
    ]


@app.post("/api/standards/{standard_id}/items", status_code=201)
def create_standard_item(
    standard_id: int, payload: StandardItemIn, session: Session = Depends(get_session)
):
    if session.get(Standard, standard_id) is None:
        raise HTTPException(404, "标准不存在")
    obj = StandardItem(
        standard_id=standard_id,
        code=payload.code,
        name=payload.name,
        unit=payload.unit,
        limit_min=payload.limit_min,
        limit_max=payload.limit_max,
    )
    session.add(obj)
    session.flush()
    return {
        "id": obj.id, "code": obj.code, "name": obj.name, "unit": obj.unit,
        "limit_min": obj.limit_min, "limit_max": obj.limit_max,
    }


# ---------------------------------------------------------------- 提交 submit

@app.post("/api/runs", status_code=201)
def submit_run(
    payload: RunIn,
    session: Session = Depends(get_session),
    _ip: None = Depends(require_intranet),
):
    """一次提交一个完整试验批次：batch + 各测试项记录 + 各记录下的测量值。

    只允许内网 IP 提交（require_intranet 校验）；公网直连返回 403。
    """
    if session.get(Sample, payload.sample_id) is None:
        raise HTTPException(404, "样品不存在")

    started = payload.started_at or datetime.now()
    run = TestRun(
        sample_id=payload.sample_id,
        run_no=payload.run_no,
        operator=payload.operator,
        started_at=started,
        environment=payload.environment,
        remark=payload.remark,
    )
    session.add(run)
    session.flush()

    record_ids = []
    for rec_in in payload.records:
        if session.get(StandardItem, rec_in.standard_item_id) is None:
            raise HTTPException(404, f"测试项 {rec_in.standard_item_id} 不存在")
        rec = TestRecord(
            test_run_id=run.id,
            standard_item_id=rec_in.standard_item_id,
            status=rec_in.status,
            started_at=started,
        )
        session.add(rec)
        session.flush()
        for m in rec_in.measurements:
            session.add(
                Measurement(
                    test_record_id=rec.id,
                    metric=m.metric,
                    value=m.value,
                    unit=m.unit,
                    text_value=m.text_value,
                )
            )
        record_ids.append(rec.id)

    return {"id": run.id, "run_no": run.run_no, "record_ids": record_ids}


@app.get("/api/runs")
def list_runs(sample_id: int | None = None, limit: int = 100,
              session: Session = Depends(get_session)):
    stmt = select(TestRun).order_by(TestRun.started_at.desc()).limit(limit)
    if sample_id is not None:
        stmt = stmt.where(TestRun.sample_id == sample_id)
    return [
        {"id": r.id, "run_no": r.run_no, "sample_id": r.sample_id,
         "operator": r.operator, "started_at": _iso(r.started_at)}
        for r in session.scalars(stmt)
    ]


@app.get("/api/runs/{run_id}")
def get_run(run_id: int, session: Session = Depends(get_session)):
    run = session.scalar(
        select(TestRun)
        .options(
            selectinload(TestRun.records).selectinload(TestRecord.standard_item),
            selectinload(TestRun.records).selectinload(TestRecord.measurements),
            selectinload(TestRun.records).selectinload(TestRecord.files),
        )
        .where(TestRun.id == run_id)
    )
    if run is None:
        raise HTTPException(404, "试验不存在")
    return {
        "id": run.id,
        "run_no": run.run_no,
        "sample_id": run.sample_id,
        "operator": run.operator,
        "started_at": _iso(run.started_at),
        "records": [
            {
                "id": r.id,
                "item_code": r.standard_item.code,
                "item_name": r.standard_item.name,
                "status": r.status,
                "measurements": [
                    {"metric": m.metric, "value": m.value, "unit": m.unit}
                    for m in r.measurements
                ],
                "files": [f.name for f in r.files],
            }
            for r in run.records
        ],
    }


# ---------------------------------------------------------------- 归档 archive

@app.post("/api/records/{record_id}/files", status_code=201)
def upload_file(
    record_id: int,
    kind: str = "raw",
    note: str | None = None,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """上传一个文件归档到该测试记录下，落在内部云文件区并登记入库。"""
    rec = session.get(TestRecord, record_id)
    if rec is None:
        raise HTTPException(404, "测试记录不存在")
    content = file.file.read()
    df = store_file(
        run_no=rec.test_run.run_no,
        filename=file.filename or "unnamed",
        content=content,
        session=session,
        test_record_id=record_id,
        kind=kind,
        note=note,
    )
    session.flush()
    return {"id": df.id, "name": df.name, "path": df.path, "kind": df.kind, "note": df.note}


@app.get("/api/records/{record_id}/files/{name}")
def download_file(record_id: int, name: str, session: Session = Depends(get_session)):
    """取回一个归档文件，让同事能把「数据库里登记的记录」对应的原始文件下载下来。"""
    df = session.scalar(
        select(DataFile).where(
            DataFile.test_record_id == record_id,
            DataFile.name == name,
        )
    )
    if df is None:
        raise HTTPException(404, "归档文件不存在")
    path = Path(df.path)
    if not path.is_file():
        raise HTTPException(404, "文件已在磁盘上缺失")
    return FileResponse(path, filename=df.name, media_type="application/octet-stream")


@app.get("/api/archive")
def list_archive(session: Session = Depends(get_session)):
    """列出所有归档文件（带批次号 / 样品号上下文）。"""
    rows = session.execute(
        select(DataFile, TestRun.run_no, Sample.code)
        .join(TestRecord, DataFile.test_record_id == TestRecord.id)
        .join(TestRun, TestRecord.test_run_id == TestRun.id)
        .join(Sample, TestRun.sample_id == Sample.id)
        .order_by(DataFile.id)
    ).all()
    return [
        {"id": f.id, "name": f.name, "path": f.path, "kind": f.kind, "note": f.note,
         "run_no": run_no, "sample_code": code}
        for f, run_no, code in rows
    ]


# ---------------------------------------------------------------- 查询 / 导出

@app.get("/api/comparison")
def comparison(metric: str, sample_id: int | None = None,
               standard_item_id: int | None = None):
    return compare_metric(metric, sample_id=sample_id, standard_item_id=standard_item_id)


@app.get("/api/judge")
def judge(metric: str, standard_item_id: int, sample_id: int | None = None):
    return judge_metric(metric, sample_id=sample_id, standard_item_id=standard_item_id)


@app.get("/api/export/case-records")
def export_case_records(sample_code: str | None = None, status: str | None = None):
    tmp = Path(tempfile.gettempdir()) / "powerdb-case-records.xlsx"
    export_case_records_to_excel(tmp, sample_code=sample_code, status=status)
    return FileResponse(tmp, media_type=_XLSX, filename="用例执行记录.xlsx")


@app.get("/api/export/judge")
def export_judge(metric: str, standard_item_id: int):
    rows = judge_metric(metric, standard_item_id=standard_item_id)
    tmp = Path(tempfile.gettempdir()) / "powerdb-judge.xlsx"
    export_judge_table(rows, tmp)
    return FileResponse(tmp, media_type=_XLSX, filename="判定结果.xlsx")


# ---------------------------------------------------------------- 维护 maintain

@app.get("/api/maintenance/health")
def health(session: Session = Depends(get_session)):
    session.execute(select(1)).scalar()  # 确认库连通
    return maintenance.health(archive_root())


@app.get("/api/maintenance/stats")
def stats():
    return maintenance.stats()


@app.post("/api/maintenance/backup")
def backup(dest_dir: str = "backups"):
    path = maintenance.backup(dest_dir)
    return {"backup_file": str(path)}