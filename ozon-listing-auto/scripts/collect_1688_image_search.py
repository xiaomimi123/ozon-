# scripts/collect_1688_image_search.py
"""AdsPower + Playwright 拍立淘图搜采集：下载 Ozon 主图 → 环境内打开 1688 拍立淘上传页 → 上传图 →
截获图搜接口响应 → POST /import/image-search {task_id, ozon_product_id, payload}。
socks5/扩展无关/1688 登录态在 AdsPower 环境内预配置。不含任何验证码绕过/反检测规避。
用法: python scripts/collect_1688_image_search.py --user-id <env> --backend http://host/api --token <import_token> \
      --task-id 1 --product-id 5 --image-url <Ozon主图URL> [--search-url <拍立淘上传页>] [--match offer/search]
"""
import argparse, json, tempfile, time, urllib.request

def _get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode())

def _post(url, body, token):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json", "X-Import-Token": token})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://local.adspower.net:50325")
    ap.add_argument("--user-id", required=True)
    ap.add_argument("--backend", required=True)   # 如 http://localhost:18080/api
    ap.add_argument("--token", required=True)      # import_token
    ap.add_argument("--task-id", type=int, required=True)
    ap.add_argument("--product-id", type=int, required=True)
    ap.add_argument("--image-url", required=True)  # Ozon 主图 URL
    ap.add_argument("--search-url", default="https://s.1688.com/youyuan/index.htm")  # 拍立淘上传页, 按实际调
    ap.add_argument("--file-input", default="input[type=file]")  # 文件 input 选择器, 按实际调
    ap.add_argument("--match", default="imageSearch,offer/search,pcImageSearch")  # 图搜接口 URL 命中子串
    ap.add_argument("--dwell", type=float, default=8.0)
    a = ap.parse_args()

    # 下载 Ozon 主图到临时文件
    img = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    with urllib.request.urlopen(a.image_url, timeout=30) as r:
        img.write(r.read())
    img.close()

    start = _get(f"{a.api}/api/v1/browser/start?user_id={a.user_id}")
    ws = start["data"]["ws"]["puppeteer"]
    subs = [x for x in a.match.split(",") if x]
    captured = {}
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(ws)
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_response(resp):
            if any(sub in resp.url for sub in subs) and not captured:
                try:
                    captured["payload"] = resp.json()
                except Exception:
                    pass
        page.on("response", on_response)

        page.goto(a.search_url, wait_until="domcontentloaded")
        try:
            page.set_input_files(a.file_input, img.name)  # 上传主图触发拍立淘; 遇滑块请人工处理
        except Exception as e:
            print("上传图片失败(检查 --file-input 选择器与页面):", e)
        time.sleep(a.dwell)
        browser.close()
    _get(f"{a.api}/api/v1/browser/stop?user_id={a.user_id}")

    if "payload" in captured:
        body = {"task_id": a.task_id, "ozon_product_id": a.product_id, "payload": captured["payload"]}
        print("回传后端:", _post(f"{a.backend.rstrip('/')}/import/image-search", body, a.token))
    else:
        print("未截获图搜响应(检查 --match 子串 / 是否触发拍立淘 / 是否遇滑块)")

if __name__ == "__main__":
    main()
