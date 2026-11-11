# -*- coding: utf-8 -*-
"""根据流水线结论组装公开包与私有审核包，并写入冻结摘要。
公开侧只允许出现泛化后的准标识字段与聚合计数；文件名保持中性，
不出现参与者码、姓名、电话或可逆对应表。以 python -I 运行。
"""
import csv
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, '/workspace')
from workbench.evidence import atomic_json, digest, manifest

ROOT = Path('/workspace')
PUBLIC = ROOT / 'public_release'
PRIVATE = ROOT / 'private_review'
EVIDENCE = ROOT / 'state/evidence'
# 仅拦截实际标识值与私有字段名；字段称谓（如“参与者码”字样）属说明文字，允许出现
FORBIDDEN_TOKENS = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9',
                    'S10', 'S11', 'S12', '合成人', '000-', 'name', 'phone',
                    'person']
PUBLIC_FIELDS = ['route_region', 'time_band', 'age_band',
                 'distinct_participants', 'observation_count']


def main():
    result = json.loads((PRIVATE / 'pipeline_result.json').read_text(encoding='utf-8'))
    evidence_manifest = json.loads(
        (ROOT / 'state/evidence/evidence_manifest.json').read_text(encoding='utf-8'))
    materials_manifest = json.loads(
        (ROOT / 'state/materials-manifest.json').read_text(encoding='utf-8'))

    PUBLIC.mkdir(exist_ok=True)
    # 公开包重跑前清空，避免残留旧文件泄漏
    for old in PUBLIC.iterdir():
        if old.is_file():
            old.unlink()

    public_rows = result['public_rows']

    # 1) 公开统计 CSV
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=PUBLIC_FIELDS)
    writer.writeheader()
    for row in public_rows:
        writer.writerow(row)
    csv_text = buf.getvalue()
    (PUBLIC / 'route_stats.csv').write_text(csv_text, encoding='utf-8', newline='')

    # 2) 公开统计 JSON
    atomic_json(PUBLIC / 'route_stats.json', {
        'freeze_at': result['freeze_at'],
        'k_threshold': 3,
        'fields': {
            'route_region': '路线片区（由具体站点/路线泛化）',
            'time_band': '出行时段（早高峰7-9/晚高峰17-19，必要时泛化为全日）',
            'age_band': '年龄段（规程给定：20-39、40-59、60+）',
            'distinct_participants': '不同参与者人数（k 按人计，不按观察行计）',
            'observation_count': '观察记录次数（同一参与者可多次）',
        },
        'rows': public_rows,
    })

    # 3) 中文发布说明
    suppressed = result['suppressed_groups']
    retained = result['retention_detail']
    withdrawn = result['withdrawn_people']
    note = f"""# RT-7 通勤路线统计——公开副本发布说明（待负责人审批，暂不对外发送）

## 1. 用途与冻结时点
- 申请课题：RT-7，用途限定为通勤路线统计，不用于保险定价等商业评估。
- 数据冻结时点：{result['freeze_at']}。所有授权与撤回均按该时点之前的生效状态解释。
- 本副本仅为发布准备件，门户草稿状态为“待人工审批”，审批通过前不得对外提供。

## 2. 数据来源与授权口径
- 来源材料：本地观察记录 materials/observations.csv（SHA-256：{result['observations_sha256']}），共 13 条观察行、12 名参与者。
- 授权解释口径：按参与者、研究用途、生效时点逐人判定。授权按文书列明的采集日期适用，
  不以最新签署的宽泛条款追溯覆盖不在范围内的旧记录；补充条款仅在其列明的采集日期内有效。
- 冻结时点前生效的“全部研究数据”撤回，其原始观察行与任何衍生统计一律留置，不进入公开副本。

## 3. 逐类处理、授权证据与数据去向
| 参与者类别 | 人数 | 处置 | 授权证据 |
| --- | --- | --- | --- |
| 授权覆盖“路线统计”且覆盖采集日期 | 7 人（逐人对应关系仅存于私有审核目录） | 泛化后参与组大小检查，达标组发布 | G1、G2、G3、G4、G6、G7、G9 |
| 冻结前撤回全部研究数据 | 2 人（逐人明细仅存于私有留置目录，公开侧不出现其编码） | 原始行与衍生行全部留置 | W5（2026-11-09 生效）、W8（2026-11-10 生效） |
| 授权用途不含本申请 | 1 人 | 留置 | G10（用途为商业评估） |
| 授权采集日期不覆盖观察日期 | 1 人 | 留置，禁止追溯适用 | G11/G11B（collected_from=2026-11-01，观察日期 2026-10-20） |
| 门户无任何同意文书 | 1 人 | 留置 | 无 |

- 全部 13 条观察行均有去向：8 条进入可发布候选（含同一参与者 2 次观察），5 条留置；
  逐行去向与证据见私有目录 retention_detail.json，公开包不含该对应关系。

## 4. 匿名化处理与最小组人数检查
- 已剔除直接标识：姓名、电话、私有参与者码均不进入公开副本；公开包不含任何可逆对应表，
  审核用对应关系保存在与公开包物理分离的私有目录。
- 泛化层级（规程允许的范围内，按真实数据选择）：
  1. 具体路线 R1-R4 → 路线片区（东片/西片/北片，R3 与 R4 合并为北片）；
  2. 整点小时 → 高峰时段（早高峰 7-9 点、晚高峰 17-19 点；其他情形泛化为全日）；
  3. 具体年龄 → 年龄段（20-39、40-59、60+）。
- 最小组人数规则：对最终可联结的准标识组合（路线片区 × 时段 × 年龄段）检查，
  人数按不同参与者计（不按观察行计），阈值 k=3。
- 检查结果（基于真实数据，非“已匿名”布尔结论）：
  - 东片 × 早高峰 × 20-39：不同参与者 3 人、观察 4 次，k=3，达标，予以发布；
  - 北片 × 早高峰 × 60+：k=2，继续将时段泛化至全日后仍为 k=2，压制，不发布该切片；
  - 西片 × 晚高峰 × 40-59：k=2，继续将时段泛化至全日后仍为 k=2，压制，不发布该切片。
- 未采用“拒绝整包发布”：存在达标的统计组；未达标组按规程选择压制而非降阈值发布。

## 5. 对统计目的的影响（信息损失说明）
- 可提供：东片早高峰 20-39 年龄段的参与者人数与观察次数，满足申请所需路线、时段、年龄层口径。
- 不可提供：北片（含原 R3、R4 路线）早高峰 60+ 切片、西片（原 R2）晚高峰 40-59 切片，
  因独立参与者不足 3 人被压制；合作课题组无法从公开副本获得这两个片区/时段/年龄层的计数，
  也无法通过差值还原（公开包不提供任何包含被压制人员的合计行）。
- 全部受压制与留置记录仍在私有审核目录留痕，便于负责人复核，不构成对外披露。

## 6. 冻结摘要与重建/恢复说明
- 授权材料（门户 JSON 附件与文书副本）、本地材料的 SHA-256 基线见私有目录 freeze_summary.json；
  公开包文件指纹见 public_manifest.json。
- 恢复或重建时先运行 scripts/04_revalidate.py：重新下载/核对门户材料指纹与本地材料指纹，
  任一授权材料发生变化（新增、撤回、修订、摘要不符）即判定冻结基线失效，
  本说明与全部发布结论作废，须重新走授权判定与组大小检查，不得沿用旧结论。
- 本文件不含参与者码、姓名、电话及任何私有映射；如发现上述内容应视为打包事故并停止发布。
"""
    (PUBLIC / 'release_notes.md').write_text(note, encoding='utf-8', newline='')

    # 4) 公开包指纹清单（清单只覆盖数据与说明文件，不自引用）
    pub_manifest = [e for e in manifest(PUBLIC)
                    if e['path'] != 'public_manifest.json']
    atomic_json(PUBLIC / 'public_manifest.json', pub_manifest)

    # 5) 公开侧泄漏扫描（参与者码、姓名、电话、私有文件名）
    leaks = []
    for p in sorted(PUBLIC.rglob('*')):
        if p.is_file():
            text = p.read_text(encoding='utf-8', errors='strict')
            for token in FORBIDDEN_TOKENS:
                if token in text:
                    leaks.append({'file': p.name, 'token': token})
    if leaks:
        raise SystemExit(f'公开包检测到禁用标识: {leaks}')

    # 6) 私有审核文件
    atomic_json(PRIVATE / 'retention_detail.json', {
        'freeze_at': result['freeze_at'],
        'retained_rows': retained,
        'retained_source_rows': result['retained_lineage'],
        'note': '留置区记录不进入公开副本，也不产生衍生统计；撤回者原始行与衍生行全部在此留痕。',
    })
    atomic_json(PRIVATE / 'correspondence_table.json', {
        'freeze_at': result['freeze_at'],
        'warning': '审核用可逆对应关系，严禁与公开包同目录或对外提供',
        'mappings': result['correspondence'],
    })

    # 门户引用（编号@摘要）与冻结基线
    portal_refs = [r['portal_reference'] for r in evidence_manifest['records']]
    freeze_summary = {
        'freeze_at': result['freeze_at'],
        'application_purpose': '路线统计',
        'observations_sha256': result['observations_sha256'],
        'materials_baseline': materials_manifest,
        'portal_evidence_baseline': [
            {'id': r['id'], 'category': r['category'],
             'portal_reference': r['portal_reference'],
             'attachment_sha256': r['attachment_sha256'],
             'document_sha256': r['document_sha256']}
            for r in evidence_manifest['records']
        ],
        'decisions': {p: {'status': d['status'], 'evidence_docs': d['evidence_docs'],
                          'withdrawal_doc': d['withdrawal_doc'], 'reason': d['reason']}
                      for p, d in result['decisions'].items()},
        'counts': {
            'observation_rows_total': 13,
            'eligible_observation_rows': len(result['eligible_lineage']),
            'retained_observation_rows': len(result['retained_lineage']),
            'eligible_distinct_persons': 7,
            'withdrawn_persons': withdrawn,
            'published_groups': len(public_rows),
            'suppressed_groups': len(suppressed),
        },
        'group_size_checks': {
            'fine_grained': result['fine_groups'],
            'region_peak_ageband': result['region_peak_band_groups'],
            'region_allday_ageband': result['region_all_day_groups'],
            'published': result['published_groups'],
            'suppressed': suppressed,
        },
        'withdrawal_residual_check': result['withdrawal_residual_check'],
        'public_files': [{'path': e['path'], 'sha256': e['sha256']} for e in pub_manifest],
        'portal_references': portal_refs,
        'invalidation_rule': ('重建时重新校验上述全部指纹；任一授权/撤回文书或本地材料变化，'
                              '本冻结摘要及其发布结论立即作废，需重新判定。'),
    }
    atomic_json(PRIVATE / 'freeze_summary.json', freeze_summary)

    print(json.dumps({'public_files': sorted(p.name for p in PUBLIC.iterdir()),
                      'private_files': sorted(p.name for p in PRIVATE.iterdir()),
                      'leak_scan': 'pass',
                      'portal_refs': len(portal_refs)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
