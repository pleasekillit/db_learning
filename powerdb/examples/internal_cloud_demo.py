"""内部云端到端演示：用 TestClient（不真的起服务器）走通 管理→提交→归档→查询/导出→维护。

也打印了生产环境对应的 curl 命令，方便照搬到内网 Windows PC 上给团队用。

运行方式（项目根目录 /workspace/powerdb 下）：
    python examples/internal_cloud_demo.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

# —— 先指向一个临时库 + 临时归档目录，避免污染正式库 ——
_ROOT = Path(__file__).resolve().parent.parent
tmp_db = _ROOT / "internal_cloud_demo.db"
tmp_archive = _ROOT / "archive_demo"
os.environ["POWERDB_URL"] = f"sqlite:///{tmp_db}"
os.environ["POWERDB_ARCHIVE_DIR"] = str(tmp_archive)

from powerdb.core.engine import create_schema, init_engine  # noqa: E402
from powerdb.api.app import app  # noqa: E402

init_engine()
create_schema(drop=True)


def section(title: str) -> None:
    print(f"\n===== {title} =====")


def main() -> None:
    client = TestClient(app)

    # 1. 管理：建项目 / 样品 / 标准 / 测试项
    section("管理 manage")
    pid = client.post("/api/projects", json={"name": "储能逆变器送审"}).json()["id"]
    sid = client.post("/api/samples", json={
        "project_id": pid, "code": "S-1001", "name": "样机1", "model": "PCS-100",
    }).json()["id"]
    std_id = client.post("/api/standards", json={
        "code": "GB/T 34120", "name": "储能变流器技术规范", "category": "国标",
    }).json()["id"]
    eff_id = client.post(f"/api/standards/{std_id}/items", json={
        "code": "EFF", "name": "额定效率", "unit": "%", "limit_min": 95.0, "limit_max": 100.0,
    }).json()["id"]
    print(f"  project={pid} sample={sid} std={std_id} item(EFF)={eff_id}")

    # 2. 提交：一次提交完整试验（batch + 记录 + 测量值）
    section("提交 submit")
    resp = client.post("/api/runs", json={
        "sample_id": sid,
        "run_no": "R-2026-001",
        "operator": "张三",
        "records": [
            {"standard_item_id": eff_id, "status": "pass",
             "measurements": [{"metric": "efficiency", "value": 96.2, "unit": "%"}]},
        ],
    }).json()
    run_id = resp["id"]
    record_id = resp["record_ids"][0]
    print(f"  run_id={run_id} record_id={record_id}")

    # 3. 归档：上传相关数据文件
    section("归档 archive")
    up = client.post(
        f"/api/records/{record_id}/files",
        params={"kind": "raw", "note": "满载效率原始波形"},
        files={"file": ("EFF_满载.parquet", b"\x00\x01\x02waveform", "application/octet-stream")},
    ).json()
    print(f"  归档文件 id={up['id']} -> {up['name']} ({up['path']})")

    # 4. 查询 / 导出
    section("查询 / 导出")
    judge = client.get("/api/judge", params={"metric": "efficiency", "standard_item_id": eff_id}).json()
    print("  判定：", [(r["run_no"], r["value"], r["verdict"]) for r in judge])
    xlsx = client.get("/api/export/case-records")
    print(f"  导出 Excel：HTTP {xlsx.status_code}，前4字节={xlsx.content[:4]!r} (xlsx即zip，应为 b'PK')")

    # 5. 维护：健康 / 统计 / 备份
    section("维护 maintain")
    print("  健康：", client.get("/api/maintenance/health").json())
    print("  统计：", client.get("/api/maintenance/stats").json())
    print("  备份：", client.post("/api/maintenance/backup", params={"dest_dir": "backups"}))

    print("\n===== 生产环境（内网 Windows PC）对应命令 =====")
    print("  启动服务： uvicorn powerdb.api.app:app --host 0.0.0.0 --port 8000")
    print("  交互文档： http://<内网IP>:8000/docs")
    print("  提交示例： curl -X POST http://<内网IP>:8000/api/runs -H \"Content-Type: application/json\" -d '{...}'")


if __name__ == "__main__":
    main()