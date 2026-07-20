# 拍立淘图搜编排脚本（AdsPower Local API + Playwright）

`collect_1688_image_search.py` 做一件事：下载 Ozon 商品主图 → 用 AdsPower **Local API** 启动一个
已经配好 socks5 代理、并在里面登录过 1688（存了 Cookie）的浏览器环境 → Playwright 通过 CDP 接管，
打开 1688「拍立淘」以图搜图上传页 → 把下载好的主图塞进页面的文件 `<input>` 触发拍立淘识别 →
Playwright 监听页面响应，命中图搜接口的那条响应体缓存下来 → 关闭 AdsPower 环境 →
把缓存的响应 POST 给后端 `POST /import/image-search`（body `{task_id, ozon_product_id, payload}`，
`X-Import-Token` 鉴权）。后端拿到 `payload` 后按 `parse_offers` + `ali1688_offer_list_path` 解析、
`dedup_and_upsert` 入库 `supply_candidates`（见 `server/app/api/importer.py`）。

脚本本身不碰代理、不碰登录态——这些全部是 **AdsPower 环境里预先配置好**的；脚本也**不做任何
验证码绕过或反检测规避**，遇到滑块只能人工处理（见下文）。

**纯手动验证，没有自动化测试**：本脚本依赖外部 AdsPower 客户端（本地 HTTP API）和真实 1688
拍立淘页面，无法在 CI/离线环境里跑。正确性靠 review 代码逻辑 + 你在自己的 AdsPower 环境里
live 跑一次确认。

## 前置条件

1. **AdsPower 客户端**已安装并登录，本地 API 默认监听 `http://local.adspower.net:50325`
   （或者你自己的地址，脚本 `--api` 参数可覆盖）。
2. 在 AdsPower 里**新建一个浏览器环境**（可以复用 `collect_1688_adspower.py` 已经建好的那个）：
   - **代理**：填你自购的 socks5（格式一般是 `host:port:user:pass`），**建议用国内住宅代理**
     （数据中心 IP 大概率被 1688 风控识别，命中率低）。
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
4. 后端 `import_token`（`X-Import-Token`）已在「货源配置」`/settings/sources` 里设置好
   （和 `collect_1688_adspower.py`/`extension/README.md` 用的是同一个 token）。

## 三个参数需要按实际抓包/审元素调

拍立淘页面的结构和接口会变，下面三个参数**默认值大概率对不上**，第一次跑之前请务必核实：

- `--search-url`：拍立淘以图搜图的上传入口页面。默认写的是 `https://s.1688.com/youyuan/index.htm`，
  但 1688 经常调整入口路径/参数，跑之前先在浏览器里手动走一遍「拍立淘」流程，把实际能打开
  上传控件的 URL 抓下来。
- `--file-input`：页面上触发拍立淘的文件 `<input type=file>` 的 CSS 选择器。默认
  `input[type=file]`，如果页面上有多个文件 input 或者上传控件是自定义组件（点击后才动态插入
  input），需要打开浏览器开发者工具审查元素，换成能唯一定位到那个 input 的选择器。
- `--match`：图搜接口 URL 的命中子串（逗号分隔，命中任意一个就缓存该响应），默认
  `imageSearch,offer/search,pcImageSearch`。打开浏览器 Network 面板，手动做一次以图搜图，
  找到真正返回商品列表的那条 XHR/Fetch 请求，把它 URL 里有代表性的一段路径填进来。

## 跑脚本

```bash
cd ozon-listing-auto
python scripts/collect_1688_image_search.py \
  --user-id <AdsPower环境ID> \
  --backend http://localhost:18080/api \
  --token <import_token> \
  --task-id 1 --product-id 5 \
  --image-url https://cdn1.ozone.ru/xxx/main.jpg \
  --search-url https://s.1688.com/youyuan/index.htm \
  --file-input "input[type=file]" \
  --match "imageSearch,offer/search,pcImageSearch"
```

参数说明：

- `--api`：AdsPower Local API 地址，默认 `http://local.adspower.net:50325`，一般不用改。
- `--user-id`：**必填**，AdsPower 环境的 User ID。
- `--backend`：**必填**，后端 API base（如 `http://localhost:18080/api`）。
- `--token`：**必填**，`X-Import-Token`，和「货源配置」里的 `import_token` 一致。
- `--task-id` / `--product-id`：**必填**，要回传给哪个任务下的哪个 Ozon 商品（对应
  `POST /import/image-search` body 里的 `task_id`/`ozon_product_id`；后端会校验该商品确实属于
  该任务，不属于会 404）。
- `--image-url`：**必填**，Ozon 商品主图的 URL，脚本会先下载到本地临时文件再上传。
- `--search-url` / `--file-input` / `--match`：见上一节，按实际调。
- `--dwell`：上传图片后停留几秒（默认 8 秒），给拍立淘识别 + 页面发出图搜请求留时间；
  网络慢或识别慢可以调大。

脚本链路：下载 `--image-url` 到本地临时 jpg → `browser/start`（AdsPower API，拿 CDP
`ws.puppeteer` 地址）→ `playwright.chromium.connect_over_cdp`（接管已启动的浏览器，不新开进程）→
在已有的第一个 tab（没有就新建）注册 `page.on("response", ...)` 监听器（URL 命中 `--match`
任一子串且尚未缓存过，就尝试 `.json()` 存进 `captured["payload"]`）→ `page.goto(--search-url)` →
`page.set_input_files(--file-input, 临时图片路径)` 触发拍立淘上传识别 → `time.sleep(--dwell)`
等图搜接口响应被截获 → `browser.close()`（关 Playwright 侧连接）→ `browser/stop`（AdsPower API，
真正关闭这个环境的浏览器进程）→ 如果截获到响应，`POST {backend}/import/image-search`
`{task_id, ozon_product_id, payload}`（头 `X-Import-Token`）；没截获到就打印提示，不会瞎传。

跑完后打开后端「审核台」/「货源候选」相关页面（或直接查 `supply_candidates` 表）看该
Ozon 商品下是否出现刚采集的候选行；也可以看后端「采集原始记录」（`GET /import/captures`）
确认这次上传确实被记了一条 `platform=ali1688` 的 capture。

## 首次成功后如何校准解析路径

后端 `POST /import/image-search` 用 `parse_offers`（`server/app/services/sources/parser_ali.py`）
按「货源配置」里的 `ali1688_offer_list_path`（默认 `data.offerList`）从截获的 `payload` 里取商品
列表。第一次真跑，如果响应里确实有商品但后端解析出 0 条（返回的 `captured`/`inserted` 是 0），
去后端「货源配置」`/settings/sources`（或 `PUT /settings/sources`）把 `ali1688_offer_list_path`
改成和拍立淘真实响应结构匹配的点路径（可以从 `GET /import/captures/{id}` 拿到那条记录的
`raw` 字段，对照真实响应结构找到列表在哪个字段下）。

## 遇到滑块 / 验证码

**本子项目不做任何验证码绕过或自动化过检测**——这是红线，脚本里没有、也不会加这类逻辑。
如果上传图片后弹出滑块验证码或其他人机校验，请打开 AdsPower 该环境的浏览器窗口，
**人工手动**完成验证，脚本会在 `time.sleep(--dwell)` 期间继续等待，验证通过后拍立淘正常出
结果，监听器照常截获响应；`--dwell` 给的时间不够的话可以调大，或者干脆人工操作完再单独
重跑一次该商品。

## 合规提醒

跑之前请先看 `docs/1688-拼多多采集-选型与成本对比.md` §8「风险与合规」：1688 用户协议一般
不允许自动化抓取，硬爬属于灰色地带，平台可能封号/封 IP。务必：

- 用**独立小号**登录 AdsPower 环境，**不要用主力账号**。
- **限速**：不要短时间内狂刷大量商品的图搜，`--dwell` 不要调太小，必要时分批、间隔来跑。
- 出现频繁验证码或异常提示时先停下来，换号/换代理/降低频率，而不是硬冲。

## live 验证

本脚本**由用户在自己的 AdsPower 环境里 live 验证**：AdsPower 拍立淘上传主图 → 截获图搜响应
回传 → 该 Ozon 商品的 `supply_candidates` 入库 → 现有评分/审核台可见。首次回传后如果解析
出的候选数是 0，按上面「首次成功后如何校准解析路径」一节调整 `ali1688_offer_list_path`。
