import os

import pytest
import sqlite3
from dotenv import load_dotenv
from sqlalchemy import insert, select

from powerdb import init_engine, DatabaseConfig, create_schema
from powerdb.models import (
    Measurement,
    Project,
    Sample,
    Standard,
    StandardItem,
    TestRecord,
    TestRun,
)

load_dotenv()  # 放在程序入口最顶部


def test_use_sqlite3_01():
    """
    使用最原始的sql脚本的形式，在原生的sqlite3库中进行数据库操作
    :return:
    """
    # db_path = r"D:\Kailing\data_base\SQLite_learning\db_demo\powerdb.db"
    db_path = os.environ.get('POWERDB_FILE')
    conn = sqlite3.connect(database=db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO measurements (test_record_id, metric, value, unit) VALUES (?, ?, ?, ?)",
        (2, "efficiency", 98.2, "%"),
    )
    conn.commit()
    cur.execute("SELECT value, unit FROM measurements WHERE metric = ?", ("efficiency",))
    print(cur.fetchall())  # [(97.2, '%')]
    conn.close()


def test_use_sqlalchemy():
    """
    根据sqlalchemy的方法进行数据库操作，仅为示例，工程化不能采用，会造成脏数据
    :return:
    """
    from sqlalchemy import create_engine, insert, select, Table, MetaData, Column, String, Float, Integer
    db_url = os.environ.get('POWERDB_URL')
    engine = create_engine(db_url)
    metadata = MetaData()
    # 这一段是手工建表，容易出错
    measurements = Table(
        "measurements", metadata,
        Column("test_record_id", Integer), Column("metric", String),
        Column("value", Float), Column("unit", String),
    )
    with engine.begin() as conn:
        conn.execute(insert(measurements).values(test_record_id=8, metric="efficiency", value=97.5, unit="%"))
        rows = conn.execute(select(measurements).where(measurements.c.metric == "efficiency"))
        print(rows.fetchall())

def test_use_sqlalchemy_01():
    """
    依赖外键的检查已经在engine模块中明确，因此这条用例会出发外键存在性检查
    :return:
    """
    from powerdb import models  # 触发所有模型注册
    from powerdb.models.result import Measurement
    from powerdb.core.engine import get_engine

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(insert(Measurement.__table__).values(test_record_id=7, metric="efficiency", value=92.2, unit="%"))
        rows = conn.execute(select(Measurement.__table__).where(Measurement.__table__.c.metric == "efficiency"))
        print(rows.fetchall())

def test_use_sqlalchemy_02():
    from powerdb.core.engine import session_scope
    from powerdb.models.result import Measurement
    db_url = os.environ.get('POWERDB_URL')
    init_engine(DatabaseConfig(url=db_url))
    # create_schema(drop=True)
    with session_scope() as session:
        project = Project(name="P3")
        sample = Sample(code="S9", name="样品2", project=project)
        std = Standard(code="GB5", name="标准2")
        item = StandardItem(code="I2", name="测试项2", unit="%", standard=std)
        session.add_all([project, sample, std, item])
        session.flush()

        run = TestRun(sample_id=sample.id, run_no="R4")
        session.add(run)
        session.flush()
        rec = TestRecord(test_run_id=run.id, standard_item_id=item.id, status="pass")
        session.add(rec)
        session.flush()
        session.add(Measurement(test_record_id=rec.id, metric="efficiency", value=95.0, unit="%"))
        # session.add(Measurement(test_record_id=rec.id, metric="efficiency", value=97.8, unit="%"))

def test_use_sqlalchemy_03():
    from powerdb.core.engine import session_scope, init_engine
    from powerdb.models import Project, Sample, Standard, StandardItem, TestRun, TestRecord, Measurement

    init_engine(DatabaseConfig(url=os.environ.get("POWERDB_URL")))

    with session_scope() as session:
        project = Project(name="P4")
        sample = Sample(code="S10", name="样品3", project=project)  # 用关系关联，不用 sample_id
        std = Standard(code="GB6", name="标准3")
        item = StandardItem(code="I3", name="测试项3", unit="%", standard=std)

        run = TestRun(run_no="R5", sample=sample)  # 关系代替 sample_id
        rec = TestRecord(status="pass", test_run=run, standard_item=item)  # 关系代替 id

        rec.measurements.append(Measurement(metric="efficiency", value=95.0, unit="%"))
        rec.measurements.append(Measurement(metric="efficiency", value=97.8, unit="%"))

        session.add_all([project, std])  # 只加两个"根"，其余靠关系级联
        # 不需要任何 flush()：SQLAlchemy 的 unit of work 会按依赖顺序自动插入并回填外键