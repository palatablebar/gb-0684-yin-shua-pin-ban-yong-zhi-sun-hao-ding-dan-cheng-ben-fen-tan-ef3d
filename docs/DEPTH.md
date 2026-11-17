# 深度登记 印刷拼版用纸损耗与订单成本分摊

规模：中型。核心规则：按版面旋转比较可排数量，固定开机损耗与印量损耗分开计，再对订单做最大余数分摊。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 工单采信 | 查看并复算工单采信 | `/api/m1_ingest` | `app/modules/m1_ingest/reader.py` | `tests/test_ingest.py` |
| M2 纸张换算 | 查看并复算纸张换算 | `/api/m2_mapping` | `app/modules/m2_mapping/rules.py` | `tests/test_mapping.py` |
| M3 拼版排算 | 查看并复算拼版排算 | `/api/m3_versions` | `app/modules/m3_versions/rules.py` | `tests/test_versions.py` |
| M4 损耗认定 | 查看并复算损耗认定 | `/api/m4_segments` | `app/modules/m4_segments/rules.py` | `tests/test_segments.py` |
| M5 余料结转 | 查看并复算余料结转 | `/api/m5_calculate` | `app/modules/m5_calculate/rules.py` | `tests/test_calculate.py` |
| M6 成本对账 | 查看并复算成本对账 | `/api/m6_reconcile` | `app/modules/m6_reconcile/compare.py` | `tests/test_reconcile.py` |
| M7 批次归档 | 查看并复算批次归档 | `/api/m7_archive` | `app/modules/m7_archive/export_out.py` | `tests/test_archive.py` |

## 陷阱登记

| TRAP | 现象 | 朴素实现 | 处理 | 处理位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-01 | GB18030中文 | 固定UTF-8失败 | 按编码链回退 | `app/modules/m1_ingest/decode.py` | `tests/test_ingest.py::test_legacy_encoding` |
| TRAP-02 | 表头BOM | 首列键失配 | 去除BOM | `app/modules/m1_ingest/decode.py` | `tests/test_ingest.py::test_bom` |
| TRAP-03 | 引号内换行 | 分行误计 | csv逻辑记录 | `app/modules/m1_ingest/reader.py` | `tests/test_ingest.py::test_preserves_multiline_note` |
| TRAP-05 | 列数错位 | 静默补列 | WIDTH隔离 | `app/modules/m1_ingest/reader.py` | `tests/test_ingest.py::test_width_isolation` |
| TRAP-06 | 全角千分位 | float失败 | NFKC与Decimal | `app/modules/m2_mapping/coerce.py` | `tests/test_mapping.py::test_thousands` |
| TRAP-07 | 空值哨兵 | 空值当零 | MISSING隔离 | `app/modules/m2_mapping/coerce.py` | `tests/test_mapping.py::test_missing_numeric` |
| TRAP-08 | 前导零ID | 编码失真 | 字符串保形 | `app/modules/m2_mapping/rules.py` | `tests/test_mapping.py::test_identifier_zeroes` |
| TRAP-10 | 浮点误差 | 累计失准 | Decimal求和 | `app/modules/m2_mapping/coerce.py` | `tests/test_mapping.py::test_decimal_precision` |
| TRAP-14 | 同版冲突 | 最后覆盖 | 整组隔离 | `app/modules/m2_mapping/rules.py` | `tests/test_mapping.py::test_real_conflict_quarantine` |
| TRAP-18 | 三种空态 | 除零或伪成功 | 三个错误码 | `app/modules/m1_ingest/reader.py` | `tests/test_ingest.py::test_empty_three_states` |
| TRAP-26 | 旧版本复核 | 覆盖新结论 | 事务条件更新 | `app/store.py` | `tests/test_archive.py::test_stale_review` |
| TRAP-15 | cm与mm | 尺寸相差10倍 | 尺寸统一mm | `app/modules/m3_versions/rules.py` | `tests/test_versions.py::test_real_cm_conversion` |
| TRAP-24 | 分币尾差 | 合计不相等 | 按纸批最大余额 | `app/modules/m5_calculate/rules.py` | `tests/test_calculate.py::test_largest_remainder` |
| TRAP-27 | 组内分币尾差 | 组成本≠成员和 | 以组成本为目标再分摊 | `app/modules/m5_calculate/rules.py` | `tests/test_ganging.py::test_apportion_with_target` |
| TRAP-28 | 急单等晚单 | 生产日被拖晚 | 组生产日取最早交期 | `app/modules/m3_versions/ganging.py` | `tests/test_ganging.py::test_proposal_same_paper_same_spec` |
| TRAP-29 | 共享损耗重复计 | 开机损耗按单收 | 全组共担一次再分摊 | `app/modules/m4_segments/rules.py` | `tests/test_ganging.py::test_auto_shared_startup_once` |
| TRAP-30 | 决定重跑 | 重复损耗成本 | 幂等键含裁决参数 | `app/main.py` | `tests/test_ganging.py::test_decide_idempotent` |
| TRAP-31 | 生成失败覆盖 | 旧版丢失 | 失败不写库 | `app/main.py` | `tests/test_ganging.py::test_decide_failure_keeps_old_version` |

## 对账规则

输入行数=采纳+隔离+空行+重复表头+完全重复；业务总数与计算证据独立求和。隔离行保留来源行、ID、原因码与原值。合版组内核对：各单分摊的损耗合计=组合计，各单成本合计=组成本，组库存扣减=组总张数；整组对账通过才允许封存与导出。

## 已知不覆盖

不做多租户权限和外部服务联调。行业规则以项目数据字典为准。文件上限2MB，逐行解析后在上限内完成分组计算。
