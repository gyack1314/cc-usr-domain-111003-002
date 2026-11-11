# -*- coding: utf-8 -*-
"""恢复/重建时的授权材料再校验。

流程：
  1. 重新通过浏览器从门户下载全部材料到独立复核目录（不触碰冻结证据目录）；
  2. 重新计算本地 materials 指纹；
  3. 与私有目录 freeze_summary.json 的冻结基线逐项比对；
  4. 任一新增、缺失、修订或摘要不符 → 判定冻结结论失效（exit 3），
     旧发布包与审批草稿证据不得继续使用，须重跑 02/03 并重建草稿。
以 python -I 运行。
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, '/workspace')
from workbench.evidence import manifest, verify

ROOT = Path('/workspace')
PRIVATE = ROOT / 'private_review'
RECHECK_DIR = ROOT / 'state/recheck_evidence'
RECHECK_MANIFEST = ROOT / 'state/recheck-evidence-manifest.json'


def main():
    freeze = json.loads((PRIVATE / 'freeze_summary.json').read_text(encoding='utf-8'))

    # 1) 重新浏览器取证（独立目录）
    if RECHECK_DIR.exists():
        for p in sorted(RECHECK_DIR.rglob('*'), reverse=True):
            if p.is_file():
                p.unlink()
            elif p.is_dir():
                p.rmdir()
    subprocess.run([sys.executable, '-I', str(ROOT / 'scripts/01_collect_evidence.py'),
                    str(RECHECK_DIR)], check=True)

    # 2) 新证据指纹
    new_manifest = manifest(RECHECK_DIR)
    RECHECK_MANIFEST.write_text(
        json.dumps(new_manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
        encoding='utf-8')
    new_em = json.loads((RECHECK_DIR / 'evidence_manifest.json').read_text(encoding='utf-8'))
    current = {r['id']: r for r in new_em['records']}
    baseline = {r['id']: r for r in freeze['portal_evidence_baseline']}

    problems = []
    added = sorted(set(current) - set(baseline))
    removed = sorted(set(baseline) - set(current))
    if added:
        problems.append({'type': 'new_portal_record', 'ids': added})
    if removed:
        problems.append({'type': 'missing_portal_record', 'ids': removed})
    for rid in sorted(set(current) & set(baseline)):
        c, b = current[rid], baseline[rid]
        if c['attachment_sha256'] != b['attachment_sha256']:
            problems.append({'type': 'attachment_changed', 'id': rid,
                             'baseline': b['attachment_sha256'],
                             'current': c['attachment_sha256']})
        if c['document_sha256'] != b['document_sha256']:
            problems.append({'type': 'document_changed', 'id': rid,
                             'baseline': b['document_sha256'],
                             'current': c['document_sha256']})
        if c['portal_reference'] != b['portal_reference']:
            problems.append({'type': 'portal_reference_changed', 'id': rid})

    # 3) 本地材料指纹
    mat_issues = verify(ROOT / 'materials', freeze['materials_baseline'])
    if mat_issues:
        problems.append({'type': 'materials_changed', 'paths': mat_issues})

    # 4) 公开包自身指纹是否仍与冻结摘要一致（清单文件自身不参与比对）
    pub_lookup = {e['path']: e['sha256']
                  for e in manifest(ROOT / 'public_release')
                  if e['path'] != 'public_manifest.json'}
    base_pub = {e['path']: e['sha256'] for e in freeze['public_files']}
    if pub_lookup != base_pub:
        problems.append({'type': 'public_package_drift',
                         'baseline': sorted(base_pub), 'current': sorted(pub_lookup)})

    report = {'freeze_at': freeze['freeze_at'],
              'checked_portal_records': len(current),
              'problems': problems,
              'verdict': 'STALE-结论作废' if problems else 'VALID-基线仍然有效'}
    out = PRIVATE / 'revalidation_report.json'
    out.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
                   encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if problems:
        print('冻结基线失效：授权材料已变化，旧结论作废，须重新处理并重建审批草稿。',
              file=sys.stderr)
        sys.exit(3)


if __name__ == '__main__':
    main()
