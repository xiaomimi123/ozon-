# scripts/collect_1688_adspower.py
"""用 AdsPower Local API 启动带 socks5/扩展/登录态的环境, Playwright 接管导航到 1688 关键词搜索页,
扩展会自动拦截搜索接口响应并回传后端。socks5/扩展/登录 Cookie 均在 AdsPower 环境内预先配置。
用法: python scripts/collect_1688_adspower.py --user-id <adspower环境ID> --keyword 连衣裙 --pages 2
"""
import argparse, time, urllib.request, json
from urllib.parse import quote

def _get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://local.adspower.net:50325")
    ap.add_argument("--user-id", required=True)
    ap.add_argument("--keyword", required=True)
    ap.add_argument("--pages", type=int, default=1)
    ap.add_argument("--dwell", type=float, default=6.0)
    a = ap.parse_args()
    start = _get(f"{a.api}/api/v1/browser/start?user_id={a.user_id}")
    ws = start["data"]["ws"]["puppeteer"]
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(ws)
        page = browser.contexts[0].pages[0] if browser.contexts[0].pages else browser.contexts[0].new_page()
        for pg in range(1, a.pages + 1):
            url = f"https://s.1688.com/selloffer/offer_search.htm?keywords={quote(a.keyword)}&beginPage={pg}"
            page.goto(url, wait_until="domcontentloaded")
            time.sleep(a.dwell)  # 等扩展拦截并回传; 遇滑块请人工处理
        browser.close()
    _get(f"{a.api}/api/v1/browser/stop?user_id={a.user_id}")
    print("done")

if __name__ == "__main__":
    main()
