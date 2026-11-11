# 私有审核目录（不得对外提供，不得与 public_release 同目录分发）

本目录保存 RT-7 发布准备的审核侧材料，公开包 `../public_release` 不含这里的任何内容。

- `correspondence_table.json`：审核用可逆对应关系（来源行、参与者码、原始路线/小时/年龄 → 泛化值、授权证据）。仅用于负责人复核与撤回追溯。
- `retention_detail.json`：留置明细。覆盖冻结前撤回（W5、W8）、用途不符（G10）、采集日期不覆盖（G11/G11B）、无同意文书四类，逐行记录授权证据与去向；留置记录不进入公开副本，也不产生衍生统计。
- `freeze_summary.json`：冻结摘要。含门户 14 份材料与本地 materials 的 SHA-256 基线、逐人授权裁决、三级组大小检查、压制决定、撤回残留检查与失效规则。
- `pipeline_result.json`：流水线完整中间结论（细粒度/泛化组大小、裁决、对应关系、残留检查）。
- `revalidation_report.json`：最近一次再校验报告（由 scripts/04_revalidate.py 生成）。

## 恢复或重建

1. 运行 `python -I scripts/04_revalidate.py`：重新通过浏览器取证并与冻结基线比对。
2. 报告 `VALID-基线仍然有效` 才可沿用本目录结论；出现 `STALE-结论作废`（任一授权/撤回文书或本地材料新增、缺失、修订、摘要不符）时，本目录与公开包的全部结论作废，须重跑 `02_prepare_release.py`、`03_package_release.py` 并重建门户草稿，不得沿用旧引用。
3. 污染演练见 `scripts/05_change_detection_drill.py`（临时门户，不触碰日常数据）。
