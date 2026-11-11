# -*- coding: utf-8 -*-
"""RT-7 通勤研究数据发布副本准备流水线（冻结时点 2026-11-10T12:00:00+08:00）。

输入：
  - 浏览器取证目录 state/evidence（门户 JSON 附件、文书副本、指纹）
  - 本地材料 materials/observations.csv、dictionary.json、policy.md、application.md
输出：
  - public_release/   公开副本（无直接标识、无参与者码、无可逆映射）
  - private_review/   私有审核目录（对应关系、留置明细、冻结摘要、校验基线）

授权按参与者、研究用途、生效时点解释；撤回者原始行与衍生行全部留置；
最终可联结准标识组合（路线片区 × 时段 × 年龄段）按不同参与者计 k>=3，
不满足者压制并记录信息损失。以 python -I 运行。
"""
import csv
import hashlib
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, '/workspace')

from workbench.domain import project, group_sizes, lineage
from workbench.evidence import atomic_json, digest, verify

ROOT = Path('/workspace')
EVIDENCE = ROOT / 'state/evidence'
EVIDENCE_MANIFEST = ROOT / 'state/evidence-manifest.json'
MATERIALS_MANIFEST = ROOT / 'state/materials-manifest.json'
PUBLIC = ROOT / 'public_release'
PRIVATE = ROOT / 'private_review'

FREEZE_AT = '2026-11-10T12:00:00+08:00'
APPLICATION_PURPOSE = '路线统计'
K_THRESHOLD = 3

# 规程给定的泛化层级
AGE_BANDS = [(20, 39, '20-39'), (40, 59, '40-59'), (60, 200, '60+')]
PEAK_WINDOWS = {'早高峰': set(range(7, 10)), '晚高峰': set(range(17, 20))}
DIRECT_IDENTIFIERS = {'name', 'phone', 'person'}


def parse_date(s: str) -> date:
    return datetime.strptime(s, '%Y-%m-%d').date()


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def age_band(age: int) -> str:
    for lo, hi, label in AGE_BANDS:
        if lo <= age <= hi:
            return label
    raise ValueError(f'年龄 {age} 不在规程可用年龄段内')


def peak_band(hour: int) -> str:
    for label, hours in PEAK_WINDOWS.items():
        if hour in hours:
            return label
    return '全日'


def sha256_file(path: Path) -> str:
    return digest(path.read_bytes())


def load_evidence_records():
    """从浏览器下载的附件 JSON 读取授权材料，并与冻结指纹核对。"""
    issues = verify(EVIDENCE, json.loads(EVIDENCE_MANIFEST.read_text(encoding='utf-8')))
    if issues:
        raise SystemExit(f'证据目录指纹不符，停止处理: {issues}')
    records = []
    for att in sorted((EVIDENCE / 'attachments').glob('*.json')):
        rec = json.loads(att.read_text(encoding='utf-8'))
        rec['_attachment_sha256'] = sha256_file(att)
        doc = EVIDENCE / 'documents' / (att.stem + '.txt')
        rec['_document_sha256'] = sha256_file(doc)
        records.append(rec)
    return records


def evaluate_consent(records, observations):
    """逐参与者、逐用途、逐采集时点判定授权状态。返回 person -> 裁决。"""
    people = sorted({r['person'] for r in observations})
    consent_docs = [r for r in records if r['category'] in ('同意', '补充')]
    withdraw_docs = [r for r in records if r['category'] == '撤回']

    # 撤回：冻结时点前生效、范围为全部研究数据
    withdrawals = {}
    for w in withdraw_docs:
        eff = parse_ts(w['fields']['effective'])
        if eff <= parse_ts(FREEZE_AT) and w['fields']['scope'] == '全部研究数据':
            withdrawals[w['fields']['person']] = w

    decisions = {}
    for person in people:
        docs = [d for d in consent_docs if d['fields']['person'] == person]
        # 被补充条款声明 supersedes 的旧文书不再作为有效授权依据
        superseded = {d['fields'].get('supersedes') for d in docs
                      if d['fields'].get('supersedes')}
        active_docs = [d for d in docs if d['id'] not in superseded]
        obs_dates = sorted({parse_date(o['date']) for o in observations
                            if o['person'] == person})
        # 补充条款可能不重列 until：沿用人/同组其他文书的有效期，否则视为长期有效
        fallback_until = max((d['fields'].get('until') for d in docs
                              if d['fields'].get('until')), default='9999-12-31')
        matched = []
        for d in active_docs:
            f = d['fields']
            covers_purpose = APPLICATION_PURPOSE in f['purpose']
            starts = parse_date(f['collected_from'])
            ends = parse_date(f.get('until', fallback_until))
            covers_dates = all(starts <= od <= ends for od in obs_dates)
            matched.append({
                'doc': d['id'],
                'purpose_match': covers_purpose,
                'collected_from': f['collected_from'],
                'until': f.get('until', fallback_until),
                'covers_observation_dates': covers_dates,
                'usable_for_application': covers_purpose and covers_dates,
                'attachment_sha256': d['_attachment_sha256'],
                'document_sha256': d['_document_sha256'],
            })
        usable = [m for m in matched if m['usable_for_application']]
        if person in withdrawals:
            w = withdrawals[person]
            status, reason = 'withdrawn', (
                f"撤回 {w['id']} 于 {w['fields']['effective']} 生效（早于冻结时点），"
                f"范围：{w['fields']['scope']}；原始行与衍生行全部留置")
            evidence = w['id']
        elif not docs:
            status, reason, evidence = 'no_consent', '门户无该参与者任何同意/补充文书', None
        elif not usable:
            # 区分用途不符与采集时点不覆盖，且不允许宽泛新条款追溯覆盖旧记录
            purpose_bad = all(not m['purpose_match'] for m in matched)
            if purpose_bad:
                status = 'purpose_out_of_scope'
                reason = '有效授权用途不含“路线统计”，授权不得推及本次申请用途'
            else:
                status = 'collection_not_covered'
                reason = ('授权列明的适用采集日期不覆盖观察记录日期；'
                          '不得用后续签署的宽泛条款追溯覆盖不在范围内的旧记录')
            evidence = ','.join(sorted(m['doc'] for m in matched))
        else:
            status, reason = 'eligible', '存在覆盖本次用途与采集时点的有效授权'
            evidence = ','.join(sorted(m['doc'] for m in matched
                                       if m['usable_for_application']))
        decisions[person] = {
            'person': person,
            'status': status,
            'reason': reason,
            'evidence_docs': evidence,
            'doc_evaluation': matched,
            'withdrawal_doc': withdrawals[person]['id'] if person in withdrawals else None,
        }
    return decisions


def main():
    records = load_evidence_records()

    # 读取观察记录（本地材料，先核指纹）
    mat_issues = verify(ROOT / 'materials',
                        json.loads(MATERIALS_MANIFEST.read_text(encoding='utf-8')))
    if mat_issues:
        raise SystemExit(f'本地材料指纹不符: {mat_issues}')
    obs_path = ROOT / 'materials/observations.csv'
    observations = []
    with obs_path.open(encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f):
            row['hour'] = int(row['hour'])
            row['age'] = int(row['age'])
            observations.append(row)
    obs_sha = sha256_file(obs_path)
    dictionary = json.loads((ROOT / 'materials/dictionary.json').read_text(encoding='utf-8'))
    region_map = dictionary['route_region']

    # 身份关联可靠性检查：参与者码格式、姓名/电话是否齐全可对应
    for o in observations:
        if not o['person'].startswith('S') or not o['person'][1:].isdigit():
            raise SystemExit(f"行 {o['row']} 参与者码格式不可靠，按规程应入留置区")
        if not o['name'] or not o['phone']:
            raise SystemExit(f"行 {o['row']} 身份关联字段缺失，按规程应入留置区")

    decisions = evaluate_consent(records, observations)

    eligible_people = {p for p, d in decisions.items() if d['status'] == 'eligible'}
    retained_people = set(decisions) - eligible_people

    # 工作台上的投影工具：先剔除直接标识，仅保留分析字段与来源行号
    analysis_rows = project(observations, ['row', 'person', 'date', 'route', 'hour', 'age'])
    eligible_rows = [r for r in analysis_rows if r['person'] in eligible_people]
    retained_rows = [r for r in analysis_rows if r['person'] in retained_people]

    # lineage 工具：撤回者/留置者的原始行去向
    retained_lineage = lineage(retained_rows, 'row')
    assert len(retained_lineage) == len(retained_rows)

    # 留置明细（私有）：每行给出授权证据与去向
    retention_detail = []
    for r in retained_rows:
        d = decisions[r['person']]
        retention_detail.append({
            'source_row': r['row'],
            'person_code': r['person'],
            'date': r['date'],
            'route': r['route'],
            'hour': r['hour'],
            'age': r['age'],
            'status': d['status'],
            'reason': d['reason'],
            'evidence_docs': d['evidence_docs'],
            'withdrawal_doc': d['withdrawal_doc'],
            'disposition': '留置（不进入公开副本，亦不产生任何衍生统计行）',
        })
    retention_detail.sort(key=lambda x: x['source_row'])

    # ---- 泛化：路线->片区、整点->高峰/全日、年龄->年龄段 ----
    generalized = []
    for r in eligible_rows:
        generalized.append({
            'source_row': r['row'],
            'person': r['person'],
            'route_region': region_map[r['route']],
            'time_band': peak_band(r['hour']),
            'age_band': age_band(r['age']),
        })

    # 泛化层级留痕（私有）：先验证细粒度组合，再逐级泛化
    fine_groups = group_sizes(
        [{'route': r['route'], 'hour': r['hour'], 'age': r['age'], 'person': r['person']}
         for r in eligible_rows],
        ['route', 'hour', 'age'], 'person')
    region_peak_band_groups = group_sizes(
        generalized, ['route_region', 'time_band', 'age_band'], 'person')

    # 全日再泛化一层（对未过 k 的组尝试更粗时段）
    generalized_all_day = [{**g, 'time_band': '全日'} for g in generalized]
    region_all_day_groups = group_sizes(
        generalized_all_day, ['route_region', 'time_band', 'age_band'], 'person')

    # 判定通过/压制：以 片区×高峰时段×年龄段 为主层级；k 按不同参与者计
    suppressed, published = [], []
    fine_people = {tuple(g['key']): g['people'] for g in fine_groups}
    allday_lookup = {tuple(g['key']): g['people'] for g in region_all_day_groups}
    for g in region_peak_band_groups:
        key = tuple(g['key'])
        distinct_people = g['people']
        allday_key = (key[0], '全日', key[2])
        allday_people = allday_lookup.get(allday_key)
        entry = {
            'route_region': key[0], 'time_band': key[1], 'age_band': key[2],
            'distinct_participants': distinct_people,
            'distinct_participants_after_time_generalization': allday_people,
        }
        if distinct_people >= K_THRESHOLD:
            entry['decision'] = '发布'
            entry['decision_note'] = f'k={distinct_people} >= {K_THRESHOLD}'
            published.append(entry)
        elif allday_people is not None and allday_people >= K_THRESHOLD:
            entry['decision'] = '泛化时段后发布'
            entry['decision_note'] = (
                f'高峰口径 k={distinct_people}<{K_THRESHOLD}；'
                f'泛化为全日后 k={allday_people}>={K_THRESHOLD}，信息损失：不再区分早晚高峰')
            published.append(entry)
        else:
            entry['decision'] = '压制'
            entry['decision_note'] = (
                f'片区×时段×年龄段 k={distinct_people}<{K_THRESHOLD}，'
                f'进一步泛化至全日 k={allday_people} 仍不足；拒绝发布该组合，'
                '信息损失：该路线片区/时段/年龄段切片不提供统计')
            suppressed.append(entry)

    # 公开统计表：通过组的不同参与者人数与观察次数（次数按观察行计）
    public_rows = []
    for entry in sorted(published, key=lambda e: (e['route_region'], e['time_band'], e['age_band'])):
        if entry['time_band'] == '全日' and entry['decision'] == '泛化时段后发布':
            members = [g for g in generalized_all_day
                       if (g['route_region'], g['time_band'], g['age_band'])
                       == (entry['route_region'], '全日', entry['age_band'])]
        else:
            members = [g for g in generalized
                       if (g['route_region'], g['time_band'], g['age_band'])
                       == (entry['route_region'], entry['time_band'], entry['age_band'])]
        distinct = len({m['person'] for m in members})
        public_rows.append({
            'route_region': entry['route_region'],
            'time_band': entry['time_band'],
            'age_band': entry['age_band'],
            'distinct_participants': distinct,
            'observation_count': len(members),
        })
        assert distinct >= K_THRESHOLD

    # ---- 私有对应关系（审核用，独立目录）----
    correspondence = []
    for r in eligible_rows:
        g = next(x for x in generalized if x['source_row'] == r['row'])
        correspondence.append({
            'source_row': r['row'],
            'person_code': r['person'],
            'original_route': r['route'],
            'route_region': g['route_region'],
            'original_hour': r['hour'],
            'time_band': g['time_band'],
            'original_age': r['age'],
            'age_band': g['age_band'],
            'consent_evidence': decisions[r['person']]['evidence_docs'],
        })
    correspondence.sort(key=lambda x: x['source_row'])

    # 撤回残留检查：公开侧任何结构都不得出现撤回参与者
    withdrawn_people = {p for p, d in decisions.items() if d['status'] == 'withdrawn'}
    public_person_leak = sorted(
        withdrawn_people & {m['person'] for m in generalized
                            if (m['route_region'], m['time_band'], m['age_band'])
                            in {(e['route_region'], e['time_band'], e['age_band'])
                                for e in published}})
    # 公开行只含泛化字段，下面写出前再次断言无直接标识/参与者码
    for row in public_rows:
        assert not (DIRECT_IDENTIFIERS & set(row))

    result = {
        'freeze_at': FREEZE_AT,
        'observations_sha256': obs_sha,
        'decisions': decisions,
        'fine_groups': fine_groups,
        'region_peak_band_groups': region_peak_band_groups,
        'region_all_day_groups': region_all_day_groups,
        'published_groups': published,
        'suppressed_groups': suppressed,
        'public_rows': public_rows,
        'retention_detail': retention_detail,
        'correspondence': correspondence,
        'withdrawn_people': sorted(withdrawn_people),
        'withdrawal_residual_check': {
            'withdrawn_in_public': public_person_leak,
            'pass': public_person_leak == [],
        },
        'retained_lineage': retained_lineage,
        'eligible_lineage': lineage(eligible_rows, 'row'),
    }
    atomic_json(PRIVATE / 'pipeline_result.json', result)
    print(json.dumps({
        'eligible_people': sorted(eligible_people),
        'retained_people': sorted(retained_people),
        'published_groups': len(public_rows),
        'suppressed_groups': len(suppressed),
        'withdrawal_residual_pass': result['withdrawal_residual_check']['pass'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
