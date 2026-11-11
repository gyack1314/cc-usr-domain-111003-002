# -*- coding: utf-8 -*-
"""交付前独立核验（只读）：
1. 公开包字段白名单、无直接标识/参与者码/可逆映射、文件名中性；
2. 用 workbench.group_sizes 对公开准标识重新联结计数，确认 k>=3；
3. 撤回者在公开统计中的残留检查（通过私有对应关系反推公开组）；
4. 私有目录与公开目录物理分离，公开清单不含私有文件；
5. 门户草稿回读：状态待人工审批、引用摘要与证据一致、正文无私有映射。
以 python -I 运行，任何一项失败即非零退出。
"""
import csv
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, '/workspace')
from workbench.domain import group_sizes
from workbench.evidence import manifest

ROOT = Path('/workspace')
PUBLIC = ROOT / 'public_release'
PRIVATE = ROOT / 'private_review'
ALLOWED_FIELDS = {'route_region', 'time_band', 'age_band',
                  'distinct_participants', 'observation_count'}
ID_TOKENS = ['合成人', '000-', 'name', 'phone', 'person']
PERSON_CODES = [f'S{i}' for i in range(1, 13)]
BASE = 'http://127.0.0.1:8765'

checks = []


def check(name, ok, detail=''):
    checks.append({'check': name, 'pass': bool(ok), 'detail': detail})
    if not ok:
        raise AssertionError(f'{name} 失败: {detail}')


# 1. 公开包文件与字段
expected_files = {'route_stats.csv', 'route_stats.json', 'release_notes.md',
                  'public_manifest.json'}
actual_files = {p.name for p in PUBLIC.iterdir() if p.is_file()}
check('公开包文件集合', actual_files == expected_files, str(sorted(actual_files)))
check('公开文件名无参与者码/标识',
      not any(any(t in name for t in ID_TOKENS + PERSON_CODES) for name in actual_files))

with (PUBLIC / 'route_stats.csv').open(encoding='utf-8', newline='') as f:
    csv_rows = list(csv.DictReader(f))
check('CSV 字段白名单', set(csv_rows[0].keys()) == ALLOWED_FIELDS,
      str(list(csv_rows[0].keys())))
stats_json = json.loads((PUBLIC / 'route_stats.json').read_text(encoding='utf-8'))
check('JSON 与 CSV 行数一致', len(stats_json['rows']) == len(csv_rows))
for r in csv_rows:
    check('CSV 无标识值', not any(t in json.dumps(r, ensure_ascii=False)
                                  for t in ID_TOKENS + PERSON_CODES), str(r))
    check('计数为正整数', int(r['distinct_participants']) >= 1
          and int(r['observation_count']) >= 1)

# 2. 重新联结公开准标识并复算组大小（按不同参与者不可得时，校验公布人数本身>=k）
# 公开侧已无参与者码，这里用私有映射重建成员集合，独立复算每个公开组的 distinct persons
priv = json.loads((PRIVATE / 'pipeline_result.json').read_text(encoding='utf-8'))
mappings = priv['correspondence']
rebuilt = group_sizes(mappings, ['route_region', 'time_band', 'age_band'], 'person_code')
rebuilt_lookup = {tuple(g['key']): g['people'] for g in rebuilt}
for r in csv_rows:
    key = (r['route_region'], r['time_band'], r['age_band'])
    k = rebuilt_lookup[key]
    check(f'联结组 k>=3: {key}', k >= 3 and k == int(r['distinct_participants']),
          f'rebuilt k={k}, published={r["distinct_participants"]}')
# 全部泛化组中未达标的必须不在公开行
published_keys = {(r['route_region'], r['time_band'], r['age_band']) for r in csv_rows}
for g in rebuilt:
    if g['people'] < 3:
        check(f'未达标组已压制: {tuple(g["key"])}', tuple(g['key']) not in published_keys)

# 3. 撤回残留：撤回者的所有来源行均不在公开组成员中
withdrawn = set(priv['withdrawn_people'])
public_members = {m['person_code'] for m in mappings
                  if (m['route_region'], m['time_band'], m['age_band']) in published_keys}
check('撤回者无公开残留', withdrawn & public_members == set(),
      f'withdrawn={sorted(withdrawn)}, intersection={sorted(withdrawn & public_members)}')
retention = json.loads((PRIVATE / 'retention_detail.json').read_text(encoding='utf-8'))
retention_people = {x['person_code'] for x in retention['retained_rows']}
check('留置人员未进入公开组', retention_people & public_members == set())
# 13 行去向完整
all_source = {f'O{i}' for i in range(1, 14)}
accounted = set(priv['retained_lineage']) | set(priv['eligible_lineage'])
check('13 行观察全部有去向', accounted == all_source,
      f'missing={sorted(all_source - accounted)}')

# 4. 私公开离：公开包任何字节不含私有文件名与参与者码
priv_names = {p.name for p in PRIVATE.iterdir()}
pub_manifest_entries = json.loads((PUBLIC / 'public_manifest.json').read_text(encoding='utf-8'))
check('公开清单不含私有文件',
      all(e['path'] not in priv_names for e in pub_manifest_entries))
for p in PUBLIC.rglob('*'):
    if p.is_file():
        text = p.read_text(encoding='utf-8')
        leaked_codes = [c for c in PERSON_CODES if c in text]
        check(f'公开文件无参与者码: {p.name}', not leaked_codes, str(leaked_codes))
# 清单与实际指纹一致
actual_manifest = [e for e in manifest(PUBLIC) if e['path'] != 'public_manifest.json']
check('公开清单指纹与实际一致', actual_manifest == pub_manifest_entries)
# 目录物理分离
check('私有目录与公开目录不同路径',
      PRIVATE.resolve() != PUBLIC.resolve()
      and not str(PRIVATE.resolve()).startswith(str(PUBLIC.resolve()))
      and not str(PUBLIC.resolve()).startswith(str(PRIVATE.resolve())))

# 5. 门户草稿回读（HTTP 取编辑页，解析状态与正文）
html = urllib.request.urlopen(f'{BASE}/draft/RT7-release-2026-11-10').read().decode('utf-8')
check('草稿状态待人工审批', '待人工审批' in html)
evidence = json.loads((ROOT / 'state/evidence/evidence_manifest.json')
                      .read_text(encoding='utf-8'))
for rec in evidence['records']:
    check(f"草稿引用含 {rec['id']}@摘要", rec['portal_reference'] in html)
# 草稿正文不得出现参与者码/直接标识（G/W 文书编号允许）
for token in PERSON_CODES + ['合成人', '000-']:
    check(f'草稿正文无 {token}', token not in html)
# 草稿列表可见
listing = urllib.request.urlopen(f'{BASE}/drafts').read().decode('utf-8')
check('草稿出现在草稿列表', 'RT-7 通勤路线统计公开副本审批草稿' in listing)
check('草稿列表标注待人工审批', '待人工审批' in listing)

report = {'total_checks': len(checks), 'all_pass': all(c['pass'] for c in checks),
          'checks': checks}
(ROOT / 'state/delivery_verification.json').write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'total_checks': len(checks),
                  'all_pass': report['all_pass']}, ensure_ascii=False, indent=2))
