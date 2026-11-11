# -*- coding: utf-8 -*-
"""通过浏览器在门户保存 RT-7 发布审批草稿（状态由门户保持“待人工审批”）。
引用全部授权/补充/撤回材料的 编号@摘要；正文只写聚合统计与处置类别，
不含参与者码、姓名、电话或私有对应关系。保存后立即回读校验。以 python -I 运行。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, '/workspace')
from playwright.sync_api import sync_playwright, expect

BASE = 'http://127.0.0.1:8765'
DRAFT_KEY = 'RT7-release-2026-11-10'

BODY = """申请课题：RT-7 通勤路线统计（不用于保险定价等商业评估）。
数据冻结时点：2026-11-10T12:00:00+08:00。本草稿不构成审批，公开副本暂不对外发送。

一、授权裁决（按参与者、用途、生效时点逐人解释，禁止宽泛条款追溯适用）
1. 7 名参与者授权覆盖路线统计且覆盖采集日期，纳入泛化与组大小检查，依据 G1、G2、G3、G4、G6、G7、G9。
2. 2 名参与者在冻结时点前撤回全部研究数据（W5、W8），原始观察行与衍生统计全部留置，公开侧无残留。
3. 1 名参与者授权用途为商业评估、不含路线统计（G10），留置。
4. 1 名参与者授权适用采集日期自 2026-11-01 起，不覆盖 2026-10-20 观察记录（G11 及替代它的 G11B），留置，不追溯适用。
5. 1 名参与者在门户无任何同意文书，留置。
观察记录共 13 行：8 行进入可发布候选（含同一参与者 2 次观察），5 行留置；逐行去向与私有对应关系存于独立私有目录，不在本草稿内。

二、匿名化与最小组人数（k=3，按不同参与者计，不按观察行计）
泛化：具体路线合并为路线片区；整点合并为早高峰/晚高峰（必要时全日）；年龄合并为 20-39、40-59、60+ 年龄段。
检查结论：
- 东片×早高峰×20-39：不同参与者 3 人、观察 4 次，k=3 达标，发布；
- 北片×早高峰×60+：k=2，时段再泛化至全日仍 k=2，压制；
- 西片×晚高峰×40-59：k=2，时段再泛化至全日仍 k=2，压制。
未采用整包拒绝发布；未达标组合按规程压制，不提供差值可还原的合计行。

三、信息损失与统计目的影响
仅东片早高峰 20-39 年龄段可提供计数；北片 60+ 与西片 40-59 两个切片因人数不足不发布，合作课题组无法获得其计数，亦无法反推。

四、交付物与冻结校验
公开包 public_release（route_stats.csv/json、release_notes.md、public_manifest.json），无直接标识、无参与者码、无可逆映射；
私有目录 private_review（审核对应关系、留置明细、冻结摘要）与公开包物理分离。
恢复或重建时运行 scripts/04_revalidate.py 重新核对门户与本地材料指纹；任一授权材料变化则本草稿引用的证据基线失效，旧结论作废。
请负责人审批；状态保持待人工审批。"""


def main():
    evidence = json.loads(Path('/workspace/state/evidence/evidence_manifest.json')
                          .read_text(encoding='utf-8'))
    refs = [r['portal_reference'] for r in evidence['records']]
    assert len(refs) == 14 and len(set(refs)) == 14

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 1280, 'height': 900})
        page.goto(f'{BASE}/draft/new', wait_until='domcontentloaded')
        page.get_by_label('草稿编号').fill(DRAFT_KEY)
        page.get_by_label('标题', exact=True).fill('RT-7 通勤路线统计公开副本审批草稿')
        page.get_by_label('正文', exact=True).fill(BODY)
        page.get_by_label('资料引用，每行一项 编号@摘要').fill('\n'.join(refs))
        page.get_by_role('button', name='保存预审草稿').click()
        expect(page.get_by_test_id('draft-status')).to_have_text('待人工审批')

        # 回读
        page.goto(f'{BASE}/draft/{DRAFT_KEY}', wait_until='domcontentloaded')
        status = page.get_by_test_id('draft-status').inner_text()
        title = page.get_by_label('标题', exact=True).input_value()
        body_back = page.get_by_label('正文', exact=True).input_value()
        refs_back = page.get_by_label('资料引用，每行一项 编号@摘要').input_value()
        page.screenshot(path='/workspace/state/evidence/pages/draft_rt7_saved.png',
                        full_page=True)
        browser.close()

    ref_lines = [line for line in refs_back.splitlines() if line.strip()]
    forbidden = ['合成人', '000-', '姓名值', 'S1', 'S2', 'S3', 'S4', 'S5',
                 'S6', 'S7', 'S8', 'S9', 'S10', 'S11', 'S12']
    # 正文中允许出现授权文书编号（G1/W5 等门户资料编号），禁止出现参与者编码与直接标识
    leaks = [t for t in forbidden if t in body_back]
    result = {
        'draft_key': DRAFT_KEY,
        'status': status,
        'title': title,
        'ref_count': len(ref_lines),
        'refs_match_evidence': sorted(ref_lines) == sorted(refs),
        'body_leaks': leaks,
        'body_length': len(body_back),
    }
    out = Path('/workspace/state/draft_readback.json')
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n',
                   encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    assert status == '待人工审批'
    assert result['refs_match_evidence']
    assert not leaks, f'草稿正文出现私有标识: {leaks}'


if __name__ == '__main__':
    main()
