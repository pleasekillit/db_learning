"""
逐步拆解表格类
"""
from powerdb.core.base import Base

def test_base_01():
    print(Base.metadata.tables.keys())


def test_base_02():
    from powerdb.models.project import Project
    obj_1 = Base.metadata.tables.keys()
    print(obj_1)

def test_base_03():
    from powerdb.models.project import Project
    obj_1 = Base.metadata.tables
    print(obj_1)

def test_base_4():
    from powerdb.models.project import Project
    print(Base.__dict__)
    print(Base.metadata.tables)
    print(Project.id)
