# -*- coding: utf-8 -*-
"""污染演练：在临时门户中修订一份授权文书，验证再校验逻辑能识别变化并作废旧结论。
不修改日常门户、portal_data 与冻结证据；结束后清理临时目录。以 python -I 运行。
（浏览器取证由 scripts/01_collect_evidence.py 覆盖；本演练专注指纹比对失效逻辑，
 临时门户附件通过同一 HTTP 接口 /attachment 下载，字节与浏览器下载一致。）
"""
import hashlib
import json
import shutil
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, '/workspace')
from workbench.portal import serving

ROOT = Path('/workspace')


def fetch(url: str) -> bytes:
    for _ in range(50):
        try:
            return urllib.request.urlopen(url, timeout=2).read()
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f'临时门户不可用: {url}')


def main():
    tmp = Path(tempfile.mkdtemp(prefix='portal-dirty-'))
    try:
        for name in ('workbench', 'portal_data'):
            shutil.copytree(ROOT / name, tmp / name)
        records_path = tmp / 'portal_data/records.json'
        records = json.loads(records_path.read_text(encoding='utf-8'))
        for rec in records:
            if rec['id'] == 'G1':
                rec['revision'] = 99
                rec['fields']['until'] = '2026-10-01'  # 制造附件摘要变化
        records_path.write_text(json.dumps(records, ensure_ascii=False, indent=2),
                                encoding='utf-8')

        with serving(tmp, tmp / 'state', port=8799) as url:
            fetch(url + '/health')
            current = {}
            for rec in records:
                body = fetch(f"{url}/attachment/{rec['id']}")
                current[rec['id']] = hashlib.sha256(body).hexdigest()

        freeze = json.loads((ROOT / 'private_review/freeze_summary.json')
                            .read_text(encoding='utf-8'))
        baseline = {r['id']: r['attachment_sha256']
                    for r in freeze['portal_evidence_baseline']}
        changed = sorted(rid for rid in baseline if current.get(rid) != baseline[rid])
        untouched = sorted(rid for rid in baseline if current.get(rid) == baseline[rid])
        result = {
            'changed_records_detected': changed,
            'unchanged_records': len(untouched),
            'invalidation_works': changed == ['G1'] and len(untouched) == 13,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        assert result['invalidation_works'], '未能正确识别授权材料变化'
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
