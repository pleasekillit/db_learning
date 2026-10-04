"""让 pytest 能把项目根目录加入 sys.path，从而 import powerdb 包。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))