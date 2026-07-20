# 1688 采集编排脚本（AdsPower Local API + Playwright）

`collect_1688_adspower.py` 只做一件事：用 AdsPower **Local API** 启动一个已经配好 socks5 代理、
加载了本仓库 `extension/` 采集扩展、并在里面登录过 1688（存了 Cookie）的浏览器环境，
Playwright 通过 CDP 接管这个环境，依次导航到 1688 关键词搜索结果页（翻页），
`extension/` 里的 `interceptor.js` 会自动拦截页面自己发出的搜索接口响应并 POST 回后端
`/import/offers`（细节见 `extension/README.md`）。脚本本身不碰代理、不碰扩展、不碰登录态——
这些全部是 **AdsPower 环境里预先配置好**的，脚本只负责"启动 + 导航 + 等回传 + 关闭"。

**纯手动验证，没有自动化测试**：本脚本依赖外部 AdsPower 客户端（本地 HTTP API）和真实 1688
页面，无法在 CI/离线环境里跑。正确性靠 review 代码逻辑 + 你在自己的 AdsPower 环境里 live 跑一次确认。

## 前置条件

1. **AdsPower 客户端**已安装并登录，本地 API 默认监听 `http://local.adspower.net:50325`
   （或者你自己的地址，脚本 `--api` 参数可覆盖）。
2. 在 AdsPower 里**新建一个浏览器环境**：
   - **代理**：填你自购的 socks5（格式一般是 `host:port:user:pass`），**建议用国内住宅代理**
     （数据中心 IP 大概率被 1688 风控识别，命中率低）。
   - **扩展**：在环境的扩展管理里加载/上传本仓库的 `extension/` 目录（未打包扩展），
     和 `extension/README.md` 里「AdsPower（或其他指纹浏览器）」一节的做法一致。
   - 打开这个环境的浏览器窗口，进扩展的「选项」页，按 `extension/README.md`「配置」一节填好
     `backendUrl`/`token`/`matchSubstr`/`keyword` 四个字段并保存。
   - **在这个环境窗口里手动登录一次 1688 账号**，让 Cookie 落到该环境的持久化 profile 里
     （AdsPower 环境退出后会保留登录态，后续脚本每次启动这个环境都是已登录状态）。
   - 记下这个环境的 **User ID**（AdsPower 环境列表里能看到，脚本 `--user-id` 要用）。
3. 本机（跑脚本的机器）安装 Playwright：
   ```bash
   pip install playwright
   playwright install chromium
   ```
   （脚本用 CDP 连接 AdsPower 已经启动的浏览器，不会自己再拉起一个 Chromium，
   但 `playwright.sync_api` 这个包本身要装；`playwright install chromium` 主要是保证依赖齐全，
   即使本地不额外起浏览器也建议装一次。）

## 跑脚本

```bash
cd ozon-listing-auto
python scripts/collect_1688_adspower.py --user-id <AdsPower环境ID> --keyword 连衣裙 --pages 2
```

参数说明：

- `--api`：AdsPower Local API 地址，默认 `http://local.adspower.net:50325`，一般不用改。
- `--user-id`：**必填**，AdsPower 环境的 User ID。
- `--keyword`：**必填**，1688 搜索关键词（会直接拼进 URL query，中文会被 urllib 自动编码）。
- `--pages`：翻几页，默认 1（对应 `s.1688.com/selloffer/offer_search.htm?...&beginPage=1..N`）。
- `--dwell`：每页导航完停留几秒（默认 6 秒），给扩展留时间拦截响应并 POST 回后端；
  网络慢或后端处理慢可以调大。

脚本链路：`browser/start`（AdsPower API，拿 CDP `ws.puppeteer` 地址）→
`playwright.chromium.connect_over_cdp`（接管已启动的浏览器，不新开进程）→
对已有的第一个 tab（没有就新建）依次 `page.goto` 搜索页 URL、`time.sleep(dwell)` 等扩展回传→
全部翻页跑完后 `browser.close()`（关 Playwright 侧连接，不等于关 AdsPower 环境）→
`browser/stop`（AdsPower API，真正关闭这个环境的浏览器进程）→打印 `done`。

跑完后打开后端 Web「导入商品」页（`/imported`）看是否出现刚采集的商品行；如果没有，
排查步骤和 `extension/README.md`「验证」一节一致（先看「采集原始记录」`/import/captures`
有没有记录，再判断是没拦到请求还是解析路径不对）。

## 遇到滑块 / 验证码

**本 PoC 不做任何验证码绕过或自动化过检测**——这是红线，脚本里没有、也不会加这类逻辑。
如果导航过程中弹出滑块验证码，请打开 AdsPower 该环境的浏览器窗口，**人工手动**完成验证，
脚本会在 `time.sleep(dwell)` 期间继续等待，验证通过后页面正常出结果，扩展照常拦截回传；
`--dwell` 给的时间不够的话可以调大，或者干脆人工操作完再单独重跑一次该关键词。

## 合规提醒

跑之前请先看 `docs/1688-拼多多采集-选型与成本对比.md` §8「风险与合规」：1688 用户协议一般
不允许自动化抓取，硬爬属于灰色地带，平台可能封号/封 IP。务必：

- 用**独立小号**登录 AdsPower 环境，**不要用主力账号**。
- **限速**：不要短时间内狂刷大量关键词/翻页，`--dwell` 不要调太小，必要时分批、间隔来跑。
- 出现频繁验证码或异常提示时先停下来，换号/换代理/降低频率，而不是硬冲。
