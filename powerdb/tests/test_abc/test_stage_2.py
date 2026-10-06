import os

import pytest
import sqlite3
from dotenv import load_dotenv

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
    根据sqlalchemy的方法进行数据库操作
    :return:
    """
    from sqlalchemy import create_engine, insert, select, Table, MetaData, Column, String, Float, Integer
    db_url = os.environ.get('POWERDB_URL')
    engine = create_engine(db_url)
    metadata = MetaData()
    measurements = Table(
        "measurements", metadata,
        Column("test_record_id", Integer), Column("metric", String),
        Column("value", Float), Column("unit", String),
    )
    with engine.begin() as conn:
        conn.execute(insert(measurements).values(test_record_id=4, metric="efficiency", value=97.2, unit="%"))
        rows = conn.execute(select(measurements).where(measurements.c.metric == "efficiency"))
        print(rows.fetchall())
