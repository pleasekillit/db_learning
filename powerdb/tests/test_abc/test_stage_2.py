import os

import pytest
import sqlite3
from dotenv import load_dotenv
from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError

from powerdb import create_schema, DatabaseConfig, get_engine, init_engine, session_scope
from powerdb.core.base import Base
from powerdb.models import (
    DataFile,
    Instrument,
    Measurement,
    Project,
    Sample,
    Standard,
    StandardItem,
    TestRecord,
    TestRun,
    TimeSeriesChannel,
    TimeSeriesPoint,
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


# ============================================================================
# 自测用例：从底层（core.base / models）向上，服务于「学基础」
#
# 学习路线：先看静态元数据（表/列/外键/索引在哪），再练最顶层 Project 的
# 独立增删改查（它没有任何外键，最省心），最后才逐层向下玩 relationship。
#
# 下面所有用例都用临时 SQLite 库（tmp_path），跑完即弃，绝不污染 powerdb.db。
# ============================================================================

# 全库所有模型，按「从顶层到底层」排列：Project 无外键 → ... → 叶子表
ALL_MODELS = [
    Project,  # 顶层：无外键
    Sample,  # -> projects
    Standard,  # 顶层：无外键
    StandardItem,  # -> standards
    Instrument,  # 顶层：无外键
    TestRun,  # -> samples
    TestRecord,  # -> test_runs / standard_items / instruments
    Measurement,  # -> test_records
    TimeSeriesChannel,  # -> test_records
    TimeSeriesPoint,  # -> timeseries_channels
    DataFile,  # -> test_records
]


@pytest.fixture()
def db(tmp_path):
    """每个用例独享一个全新的临时库：重初始化引擎 + 建表，用例结束再拆除。"""
    init_engine(DatabaseConfig(url=f"sqlite:///{tmp_path / 'stage2_selftest.db'}"))
    create_schema(drop=True)
    yield
    create_schema(drop=True)


# --- 一、core/base 与模型元数据：不开库，先看清「表长什么样」 ---------------

def test_base_metadata_registers_all_tables():
    """Base.metadata 是所有表的唯一事实来源：models 一导入，表就全注册好了。"""
    expected = {m.__tablename__ for m in ALL_MODELS}

    print(expected)
    obj_1 = Base.metadata.tables.keys()
    print(obj_1)
    assert expected <= set(obj_1)


def test_every_model_maps_to_a_table():
    """每个模型类 = 一张表；model.__tablename__ 就是表名。"""
    for model in ALL_MODELS:
        assert model.__tablename__ in Base.metadata.tables
        assert model.__table__ is Base.metadata.tables[model.__tablename__]


def test_primary_key_is_id():
    """约定：所有表主键都叫 id（单主键）。"""
    for model in ALL_MODELS:
        pk_cols = [c.name for c in model.__table__.primary_key.columns]
        assert pk_cols == ["id"]


def test_foreign_key_targets_top_down():
    """一张表看清整条外键链——就是让你头疼的那些依赖，其实可以静态列出来。"""

    def fk_targets(model):
        # parent.name = 本表列名；target_fullname = 指向的「表.列」
        return {fk.parent.name: fk.target_fullname for fk in model.__table__.foreign_keys}

    assert fk_targets(Project) == {}  # 顶层表，零外键
    assert fk_targets(Standard) == {}
    assert fk_targets(Instrument) == {}
    assert fk_targets(Sample) == {"project_id": "projects.id"}
    assert fk_targets(StandardItem) == {"standard_id": "standards.id"}
    assert fk_targets(TestRun) == {"sample_id": "samples.id"}
    assert fk_targets(TestRecord) == {
        "test_run_id": "test_runs.id",
        "standard_item_id": "standard_items.id",
        "instrument_id": "instruments.id",
    }
    assert fk_targets(Measurement) == {"test_record_id": "test_records.id"}
    assert fk_targets(TimeSeriesChannel) == {"test_record_id": "test_records.id"}
    assert fk_targets(TimeSeriesPoint) == {"channel_id": "timeseries_channels.id"}
    assert fk_targets(DataFile) == {"test_record_id": "test_records.id"}


def test_foreign_key_columns_are_indexed():
    """外键列都建了索引（index=True）——联表查询快的原因。"""
    indexed = {
        Sample: ["project_id"],
        StandardItem: ["standard_id"],
        TestRun: ["sample_id"],
        TestRecord: ["test_run_id", "standard_item_id"],
        Measurement: ["test_record_id"],
        TimeSeriesChannel: ["test_record_id"],
        TimeSeriesPoint: ["channel_id"],
        DataFile: ["test_record_id"],
    }
    for model, cols in indexed.items():
        for col in cols:
            assert model.__table__.c[col].index is True, f"{model.__name__}.{col} 未建索引"


def test_timestamp_mixin_adds_created_and_updated():
    """TimestampMixin 统一给每张表补上 created_at / updated_at，且非空。"""
    for model in ALL_MODELS:
        table = model.__table__
        assert "created_at" in table.c and "updated_at" in table.c
        assert table.c.created_at.nullable is False
        assert table.c.updated_at.nullable is False


# --- 二、顶层表 Project 的独立 CRUD：没有外键，增删改查最自由 ----------------

def test_project_create_and_read_back(db):
    """最顶层表的插入 + 查询：完全不用管任何外键。"""
    with session_scope() as session:
        session.add(Project(name="P-SELFTEST", description="顶层表自测"))

    with session_scope() as session:
        project = session.scalar(select(Project).where(Project.name == "P-SELFTEST"))
        assert project is not None
        assert project.id is not None
        assert project.description == "顶层表自测"
        # created_at / updated_at 由数据库 server_default 生成
        assert project.created_at is not None
        assert project.updated_at is not None


def test_project_update(db):
    """改：拿出对象、改属性、退出 session_scope 时自动 commit。"""
    with session_scope() as session:
        session.add(Project(name="P-UPDATE", description="旧描述"))

    with session_scope() as session:
        project = session.scalar(select(Project).where(Project.name == "P-UPDATE"))
        project.description = "新描述"

    with session_scope() as session:
        project = session.scalar(select(Project).where(Project.name == "P-UPDATE"))
        assert project.description == "新描述"


def test_project_delete(db):
    """删：顶层表没有子表依赖，可以直接删。"""
    with session_scope() as session:
        session.add(Project(name="P-DELETE"))

    with session_scope() as session:
        project = session.scalar(select(Project).where(Project.name == "P-DELETE"))
        session.delete(project)

    with session_scope() as session:
        assert session.scalar(select(Project).where(Project.name == "P-DELETE")) is None


def test_project_name_unique_conflict(db):
    """name 有唯一约束：重复插入在 commit 时报 IntegrityError，并自动回滚。"""
    with session_scope() as session:
        session.add(Project(name="P-UNIQUE"))

    with pytest.raises(IntegrityError):
        with session_scope() as session:
            session.add(Project(name="P-UNIQUE"))  # 第二次同名 → 唯一约束冲突

    with session_scope() as session:
        count = session.scalar(
            select(func.count()).select_from(Project).where(Project.name == "P-UNIQUE")
        )
        assert count == 1  # 冲突那条被回滚，只剩第一条


def test_session_scope_rolls_back_on_error(db):
    """session_scope 内抛异常 → 整段事务回滚，之前 add 的数据不会留下。"""
    with pytest.raises(RuntimeError):
        with session_scope() as session:
            session.add(Project(name="P-ROLLBACK"))
            raise RuntimeError("故意报错，验证自动回滚")

    with session_scope() as session:
        assert session.scalar(select(Project).where(Project.name == "P-ROLLBACK")) is None


def test_get_engine_enables_sqlite_foreign_keys(db):
    """engine 注册了 PRAGMA foreign_keys=ON，所以这条链的外键才会真的被校验。"""
    with get_engine().connect() as conn:
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1


# --- 三、向下逐层搭关系：relationship 会自动回填外键 ----------------------

def test_relationship_fills_foreign_key_automatically(db):
    """从顶层 Project 挂上 Sample：只 add 根对象，外键由 relationship 自动回填。"""
    with session_scope() as session:
        project = Project(name="P-REL")
        sample = Sample(code="S-REL", name="样品", project=project)  # 不写 project_id
        session.add(project)  # 只加根

    with session_scope() as session:
        sample = session.scalar(select(Sample).where(Sample.code == "S-REL"))
        assert sample.project_id is not None  # 外键被自动写上
        assert sample.project.name == "P-REL"  # 子 → 父 反向导航
        assert [s.code for s in sample.project.samples] == ["S-REL"]  # 父 → 子


def test_cascade_delete_from_test_run(db):
    """TestRun.records 配了 cascade='all, delete-orphan'：删父会自动删子。
    只需 add 两个根（Project、Standard），整条链自动按依赖顺序插入。"""
    with session_scope() as session:
        project = Project(name="P-CASCADE")
        sample = Sample(code="S-CASCADE", name="样品", project=project)
        std = Standard(code="GB-CASCADE", name="标准")
        item = StandardItem(code="I-CASCADE", name="测试项", unit="%", standard=std)
        run = TestRun(run_no="R-CASCADE", sample=sample)
        rec = TestRecord(status="pass", test_run=run, standard_item=item)
        rec.measurements.append(Measurement(metric="efficiency", value=97.5, unit="%"))
        session.add_all([project, std])  # 只加根

    with session_scope() as session:
        run = session.scalar(select(TestRun).where(TestRun.run_no == "R-CASCADE"))
        assert len(run.records) == 1
        session.delete(run)  # 级联：records → measurements 一起删

    with session_scope() as session:
        assert session.scalar(select(func.count()).select_from(TestRecord)) == 0
        assert session.scalar(select(func.count()).select_from(Measurement)) == 0


def test_delete_project_blocked_by_foreign_key(db):
    """对比：Project.samples 没配级联删除，删掉仍有 Sample 的 Project 会被外键挡住。
    这就是「删父被拒」的真实原因——要么先删子，要么给关系配 cascade。"""
    with session_scope() as session:
        project = Project(name="P-BLOCK")
        session.add(project)
        session.add(Sample(code="S-BLOCK", name="样品", project=project))

    with pytest.raises(IntegrityError):
        with session_scope() as session:
            project = session.scalar(select(Project).where(Project.name == "P-BLOCK"))
            session.delete(project)  # 子表还有引用 → 拒删
