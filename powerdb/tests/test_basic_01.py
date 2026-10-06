"""
基础读写测试：证明骨架端到端可跑。
不使用Pytest的默认路径
Author：凌楷
"""
import os
import pytest
from dotenv import load_dotenv
load_dotenv()  # 放在程序入口最顶部
from sqlalchemy import func, select

from powerdb.config import DatabaseConfig
from powerdb.core.engine import create_schema, init_engine, session_scope
from powerdb.models import (
    Measurement,
    Project,
    Sample,
    Standard,
    StandardItem,
    TestRecord,
    TestRun,
)


@pytest.fixture()
def db():
    # 此处使用默认路径
    cfg = DatabaseConfig(echo=True)

    init_engine(cfg)
    create_schema(drop=True)
    yield cfg
    # 不进行后置清理，否则结果只有空表格
    # create_schema(drop=True)


def test_write_and_read(db):
    with session_scope() as session:
        project = Project(name="P1")
        sample = Sample(code="S2", name="样品2", project=project)
        std = Standard(code="GB21", name="标准21")
        item = StandardItem(code="I21", name="测试项21", unit="%", standard=std)
        session.add_all([project, sample, std, item])
        session.flush()

        run = TestRun(sample_id=sample.id, run_no="R2")
        session.add(run)
        session.flush()
        rec = TestRecord(test_run_id=run.id, standard_item_id=item.id, status="pass")
        session.add(rec)
        session.flush()
        session.add(Measurement(test_record_id=rec.id, metric="efficiency", value=97.0, unit="%"))

    with session_scope() as session:
        run_count = session.scalar(select(func.count()).select_from(TestRun))
        assert run_count == 1

        m = session.scalar(select(Measurement).where(Measurement.metric == "efficiency"))
        assert m is not None
        assert m.value == 99.0

def test_db_cfg(db):
    """
    测试DatabaseConfig的行为
    :param db:
    :return:
    """
    cfg=db
    print(cfg)
    print(cfg.url)
    print(cfg.echo)

def test_os():
    """
    验证.env文件可以被load_dotenv()进入os.environ中
    :return:
    """
    env=os.environ
    for k,v in env.items():
        print(f"{k}: {v}")
