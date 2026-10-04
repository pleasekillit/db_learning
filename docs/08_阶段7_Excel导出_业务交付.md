# 阶段 7 · Excel 导出：面向非技术业务的交付

> 业务人员（电力电子硬件工程师）不关心代码、也不喜欢专业的数据库词汇，
> 他们只认 Excel 这种「能直接掌控的对象」。
> 本章解决：**数据库怎么把「用例编号 / 用例名称 / 执行时间 / 执行结果 / 相关数据文件」存进去，
> 再一键导出成业务一眼能看懂的 Excel。**
>
> 核心思想：**表格设计和数据库设计不割裂——用一张「字段映射表」把业务词汇、Excel 列名、
> 数据库字段三者钉在一起。**

## 本章目标
- 说清楚「业务眼里的表格」和「数据库里的表」怎么对应，而不是各写各的。
- 用一张字段映射表（`field_map.py`）统一业务词汇 ↔ Excel 列名 ↔ 数据库字段。
- 把用例执行记录（含相关数据文件）导出成带中文表头、冻结首行、结果中文化的 .xlsx。

## 为什么业务和数据库会「对不上」？

业务说：**「把这次试验的用例编号、执行结果给我导出来。」**
数据库里却是：`test_records.status`、`standard_items.code`。

如果开发直接用字段名导出，业务看到一堆 `status`、`started_at`，第一时间就懵了。
所以必须有一张「翻译表」，把三种语言对齐：

| 业务眼里的列（中文） | Excel 表头 | 数据库字段 | 说明 |
| --- | --- | --- | --- |
| 用例编号 | 用例编号 | `standard_items.code` | 测试项编号，如 `EFF` |
| 用例名称 | 用例名称 | `standard_items.name` | 测试项名称，如 `额定效率` |
| 执行时间 | 执行时间 | `test_records.started_at` | 用例开始执行时间 |
| 执行结果 | 执行结果 | `test_records.status` | `pass/fail/pending` → `通过/失败/待执行` |
| 相关数据文件 | 相关数据文件 | `data_files.name` | 每个用例关联的文件名 |

> 这张映射表就是代码里的 `exporters/field_map.py`，它既是「文档」又是「程序」：
> 导出时按它生成表头、按它从查询结果里取数。**业务要加一列，只改这一处。**

## 对应代码位置

| 内容 | 对应代码 |
| --- | --- |
| 字段映射表（业务 ↔ 库 ↔ Excel） | `powerdb/exporters/field_map.py` 的 `CASE_RECORD_FIELDS` |
| 业务视图查询（拼出中文语义的行） | `powerdb/repositories/export_repository.py` 的 `query_case_records()` |
| Excel 写入（表头/样式/冻结/中文化） | `powerdb/exporters/excel_exporter.py` |
| 相关数据文件模型 | `powerdb/models/data_file.py` 的 `DataFile` |
| 单入口导出函数 | `excel_exporter.export_case_records_to_excel()` |
| 演示 / 测试 | `examples/export_demo.py`、`tests/test_export.py` |

## 基础知识详解

### 1. 「表格设计」和「数据库设计」为什么不割裂

- **表格设计**：是给业务看的「列名 + 行」布局，属于沟通界面。
- **数据库设计**：是给程序用的「表 + 字段 + 关系」，属于存储结构。

两者本就是对同一件事的两种视角。不割裂的做法是：**让数据库里每个业务关心的字段，
都在导出映射表里有一个中文名和一句人话解释**。映射表就是它们的「共同底座」，
谁变谁同步，业务和开发看同一张表就不会各说各话。

### 2. 相关数据文件怎么存、怎么导

高频原始波形、报告、日志这类文件体积大、不适合塞进关系表，所以：
- 文件本体落磁盘（`DataFile.path` 存真实路径，给程序/现场调取用）；
- 数据库只存「给业务看的文件名」+ 类型 + 路径索引（`DataFile` 表）；
- 导出 Excel 时只把 `name` 拼成「相关数据文件」一列（多个用 `; ` 分隔）。

这样业务在 Excel 里看到的是「EFF_原始波形.parquet; EFF_报告.pdf」这种可读文件名，
需要原始文件时又能凭同一行记录反查 `path`。

```text
TestRecord(一次用例执行)
  └─ DataFile(相关数据文件：name 给业务看 / path 给程序用 / kind 分类)
```

### 3. 执行结果怎么「中文化」

数据库存的是机器的 `pass/fail/pending`（好比较、好筛选）；导出时翻译成
`通过/失败/待执行`（业务一眼懂）。这个翻译集中在 `excel_exporter._STATUS_TEXT`。

### 4. Excel 为什么不用 pandas、用 openpyxl

- pandas 的 `to_excel` 底层也得靠 openpyxl/xlsxwriter 当引擎；
- 直接 openpyxl 能精确控制**表头加粗、列宽自适应、冻结首行**，这正是「一目了然」的观感来源；
- 依赖更轻，不强行引入 pandas。

## 训练 Demo 详解

**准备**（项目根目录 `/workspace/powerdb` 下）：
```bash
pip install openpyxl
```

**任务一（导出演示）**：
```bash
python examples/export_demo.py
```
会在 `exports/用例执行记录.xlsx` 生成一张表，表头为：
`用例编号 | 用例名称 | 样品编号 | 试验编号 | 执行时间 | 执行结果 | 相关数据文件`，
执行结果已中文化为「通过」，相关数据文件一列显示多个文件名。

**任务二（看懂映射表）**：打开 `powerdb/exporters/field_map.py`，对着 `CASE_RECORD_FIELDS`
逐条确认「业务词汇 ↔ 数据库字段」；练习给业务加一列「测量值」，需要动几个文件。

**任务三（带条件导出）**：在导出入口传 `run_no="RUN-2026-001"` 或 `status="pass"`，
理解「同一个查询、不同过滤」如何复用同一段导出逻辑。

**验证标准**：业务不用懂任何数据库概念，打开 Excel 就能对「哪条用例、什么结果、
对应哪些文件」一目了然。

## 官方文档链接
- openpyxl（xlsx 读写与样式）：https://openpyxl.readthedocs.io/
- Excel 文件格式与列宽/冻结等最佳实践：https://openpyxl.readthedocs.io/en/stable/styles.html

## 学习笔记

### 日常踩坑记录（Pitfalls）
| 日期 | 现象/问题 | 原因 | 解决/结论 |
| --- | --- | --- | --- |
| 示例 | 导出 `status` 显示 pass，业务看不懂 | 库与界面语义未分离 | 导出层用 `_STATUS_TEXT` 翻译成中文 |
| 示例 | 文件列显示的是磁盘路径，太啰嗦 | 把 `path` 而非 `name` 给了业务 | 只看 `DataFile.name`，路径保持给程序 |
| 示例 | 同一用例跑多行，业务分不清 | 缺上下文列 | 映射表补「样品编号/试验编号」两列 |
|  |  |  |  |

### 学习待办（Todo）
- [ ] 跑通 `examples/export_demo.py` 并打开生成的 Excel 检查表头与内容
- [ ] 对着 `field_map.py` 给业务加一列（如「测量值」），跑一遍导出确认生效
- [ ] 试一次带 `run_no` / `status` 条件的定向导出