"""内部云 REST 服务的接口测试（TestClient，不起真服务器）。

覆盖四大能力：管理 / 提交 / 归档 / 维护；断言结果的正确性。
"""
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from powerdb.config import DatabaseConfig
from powerdb.core.engine import create_schema, init_engine


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("POWERDB_ARCHIVE_DIR", str(tmp_path / "archive"))
    init_engine(DatabaseConfig(url=f"sqlite:///{tmp_path / 'cloud.db'}"))
    create_schema(drop=True)

    from powerdb.api.app import app

    return TestClient(app)


def test_manage_submit_archive_query_maintain(client, tmp_path):
    # 管理：建项目/样品/标准/测试项
    pid = client.post("/api/projects", json={"name": "P"}).json()["id"]
    sid = client.post("/api/samples", json={
        "project_id": pid, "code": "S1", "name": "样品1", "model": "M",
    }).json()["id"]
    std_id = client.post("/api/standards", json={"code": "GB", "name": "标准"}).json()["id"]
    item_id = client.post(f"/api/standards/{std_id}/items", json={
        "code": "EFF", "name": "额定效率", "unit": "%", "limit_min": 95.0,
    }).json()["id"]

    # 提交
    resp = client.post("/api/runs", json={
        "sample_id": sid, "run_no": "R1",
        "records": [{"standard_item_id": item_id, "status": "pass",
                     "measurements": [{"metric": "efficiency", "value": 94.0, "unit": "%"}]}],
    })
    assert resp.status_code == 201
    run_id = resp.json()["id"]
    record_id = resp.json()["record_ids"][0]

    # 归档：上传文件
    up = client.post(
        f"/api/records/{record_id}/files",
        params={"kind": "raw"},
        files={"file": ("wave.parquet", b"ABC", "application/octet-stream")},
    )
    assert up.status_code == 201
    assert up.json()["name"] == "wave.parquet"
    archived = tmp_path / "archive" / "R1" / "wave.parquet"
    assert archived.read_bytes() == b"ABC"

    # 归档：下载文件（取回）
    dl = client.get(f"/api/records/{record_id}/files/wave.parquet")
    assert dl.status_code == 200
    assert dl.content == b"ABC"
    assert client.get(f"/api/records/{record_id}/files/nope.parquet").status_code == 404

    # 查询 / 判定
    judge = client.get("/api/judge", params={"metric": "efficiency", "standard_item_id": item_id}).json()
    assert judge[0]["value"] == 94.0
    assert judge[0]["verdict"] == "不合格"  # 94 < 95

    # 导出
    xlsx = client.get("/api/export/case-records")
    assert xlsx.status_code == 200
    assert xlsx.content[:4] == b"PK\x03\x04"  # xlsx 即 zip

    # 维护
    health = client.get("/api/maintenance/health").json()
    assert health["ok"] is True
    stats = client.get("/api/maintenance/stats").json()
    assert stats["test_runs"] == 1
    assert stats["data_files"] == 1
    backup = client.post("/api/maintenance/backup", params={"dest_dir": str(tmp_path / "bak")}).json()
    assert Path(backup["backup_file"]).exists()


def test_runs_requires_intranet():
    from powerdb.api.deps import is_intranet_ip

    # 内网 / 本机 / 单测来源放行
    assert is_intranet_ip("192.168.1.10") is True
    assert is_intranet_ip("10.20.30.40") is True
    assert is_intranet_ip("127.0.0.1") is True
    assert is_intranet_ip("testclient") is True
    # 公网直连拒绝
    assert is_intranet_ip("8.8.8.8") is False
    assert is_intranet_ip("1.2.3.4") is False