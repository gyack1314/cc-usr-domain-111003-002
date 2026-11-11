# -*- coding: utf-8 -*-
"""通过本地门户的浏览器界面取证：翻页阅读、进入详情、下载 JSON 附件与文书副本。
仅通过 HTTP 门户与浏览器 DOM 获取材料，不读取 portal_data 种子文件。
以 python -I 运行；下载目录与脚本目录分离，路径由参数传入。
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, '/workspace')

from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:8765'


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main(out_dir: str) -> None:
    out = Path(out_dir)
    att_dir = out / 'attachments'
    doc_dir = out / 'documents'
    page_dir = out / 'pages'
    for d in (att_dir, doc_dir, page_dir):
        d.mkdir(parents=True, exist_ok=True)

    manifest = {'base_url': BASE, 'records': [], 'list_pages': []}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
        ctx = browser.new_context(viewport={'width': 1280, 'height': 720},
                                  accept_downloads=True)
        page = ctx.new_page()

        # 1) 翻页阅读目录，从 DOM 收集资料编号（不接触种子数据）
        record_ids = []
        page_no = 1
        while True:
            page.goto(f'{BASE}/?page={page_no}', wait_until='domcontentloaded')
            rows = page.locator('tr[data-record-id]')
            count = rows.count()
            if count == 0:
                break
            page.screenshot(path=str(page_dir / f'list_p{page_no}.png'),
                            full_page=True)
            manifest['list_pages'].append({
                'page': page_no,
                'count_text': page.get_by_test_id('count').inner_text(),
            })
            for i in range(count):
                rid = rows.nth(i).get_attribute('data-record-id')
                if rid not in record_ids:
                    record_ids.append(rid)
            page_no += 1

        # 2) 逐条进入详情页阅读并下载
        for rid in record_ids:
            page.goto(f'{BASE}/record/{rid}', wait_until='domcontentloaded')
            page.screenshot(path=str(page_dir / f'record_{rid}.png'),
                            full_page=True)
            detail_text = page.locator('main').inner_text()
            shown_ref = page.get_by_test_id('reference').inner_text()
            shown_digest = page.get_by_test_id('digest').inner_text()
            assert shown_ref == rid + '@' + shown_digest

            # 下载 JSON 原始材料附件
            with page.expect_download() as ev:
                page.get_by_role('link', name='下载原始材料').click()
            att_path = att_dir / f'{rid}.json'
            ev.value.save_as(str(att_path))
            att_bytes = att_path.read_bytes()
            att_sha = sha256_bytes(att_bytes)
            assert att_sha == shown_digest, f'{rid} 附件摘要与门户展示不一致'

            # 下载文书/扫描副本
            with page.expect_download() as ev2:
                page.get_by_role('link', name='下载文书或扫描副本').click()
            doc_name = ev2.value.suggested_filename
            doc_path = doc_dir / doc_name
            ev2.value.save_as(str(doc_path))
            doc_bytes = doc_path.read_bytes()
            doc_sha = sha256_bytes(doc_bytes)

            record = json.loads(att_bytes.decode('utf-8'))
            manifest['records'].append({
                'id': rid,
                'category': record['category'],
                'title': record['title'],
                'revision': record['revision'],
                'fields': record['fields'],
                'portal_reference': shown_ref,
                'attachment_file': f'attachments/{rid}.json',
                'attachment_sha256': att_sha,
                'document_file': f'documents/{doc_name}',
                'document_sha256': doc_sha,
                'detail_text_excerpt': detail_text[:400],
            })

        # 3) 草稿列表页取证（确认初始状态）
        page.goto(f'{BASE}/drafts', wait_until='domcontentloaded')
        page.screenshot(path=str(page_dir / 'drafts_initial.png'),
                        full_page=True)
        manifest['drafts_initial_text'] = page.locator('main').inner_text()
        browser.close()

    manifest['records'].sort(key=lambda r: r['id'])
    out_path = out / 'evidence_manifest.json'
    out_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2)
        + '\n', encoding='utf-8')
    print(json.dumps({
        'records_collected': len(manifest['records']),
        'manifest': str(out_path),
    }, ensure_ascii=False))


if __name__ == '__main__':
    main(sys.argv[1])
