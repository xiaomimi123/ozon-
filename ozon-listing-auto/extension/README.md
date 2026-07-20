# Ozon 货源采集器 (1688 采集 PoC · Chrome MV3 扩展)

在 1688 页面里 hook 页面自身的 `fetch`/`XMLHttpRequest`，拦截命中「搜索/列表」类接口的响应 JSON，原样 POST 到本项目后端的采集入口 `POST /import/offers`，由后端存原始记录并按可配路径解析入库。**纯手动验证，没有自动化测试**——本文档就是验证步骤。

## 原理与文件

- `interceptor.js`（**主世界**，页面自己的 JS 上下文）：改写 `window.fetch` 与 `XMLHttpRequest.prototype.open/send`，当请求 URL 命中 `data-match` 指定的子串（逗号分隔，任一命中即可）时，把响应体当 JSON 解析后 `window.postMessage({ __ozonCollector: true, payload })` 广播出去。必须跑在主世界才能拦到页面自己发出的请求（content script 默认跑在隔离世界，hook 不到）。
- `content.js`（**隔离世界** content script，`document_start` 注入）：从 `chrome.storage.sync` 读 `matchSubstr`，动态创建 `<script src="chrome.runtime.getURL('interceptor.js')" data-match="...">` 插入页面，把 `interceptor.js` 提升到主世界执行；同时监听 `window.message` 事件，收到 `__ozonCollector` 标记的消息后用 `chrome.runtime.sendMessage({ type: "capture", payload })` 转发给 background。
- `background.js`（service worker）：收到 `type: "capture"` 消息后，从 `chrome.storage.sync` 读 `backendUrl`/`token`/`keyword`，POST 到 `<backendUrl>/import/offers?keyword=<keyword>`，带请求头 `X-Import-Token: <token>`，body 为拦截到的原始 JSON。`backendUrl`/`token` 任一为空则直接跳过，不发请求。
- `options.html` + `options.js`：扩展的设置页（`options_page`），四个字段 `backendUrl`/`token`/`matchSubstr`/`keyword`，用 `chrome.storage.sync` 读写，字段名与 `content.js`/`background.js` 里读取的键完全一致。

链路：`1688 页面请求` → `interceptor.js`(主世界 hook) → `postMessage` → `content.js`(隔离世界，转发) → `chrome.runtime.sendMessage` → `background.js`(service worker) → `fetch POST` → 后端 `/import/offers`。

## 安装（Chrome / 兼容 Chromium 内核的指纹浏览器）

1. 打开 `chrome://extensions`，右上角打开「开发者模式」。
2. 点「加载已解压的扩展程序」，选择本仓库的 `extension/` 目录。
3. 扩展列表里找到「Ozon 货源采集器 (1688 PoC)」，点「详情」→「扩展程序选项」，或直接在扩展图标右键选「选项」，打开设置页。

### AdsPower（或其他指纹浏览器）

AdsPower 内置浏览器基于 Chromium，同样支持加载未打包扩展：在浏览器环境的扩展管理里添加/上传本地扩展，选择**同一个** `extension/` 目录即可。设置页填法与 Chrome 一致，见下节。注意每个 AdsPower 环境的扩展设置是独立存储的（`chrome.storage.sync`/`local` 按 profile 隔离），换环境要重新填一次 options。

## 配置（options 页四个字段）

- **后端地址 `backendUrl`**：本项目后端的可访问地址，**要带 `/api` 前缀**（`/api` 前缀是 `web` 容器里 nginx 反代加的，不是 FastAPI 应用自己的路径）。例如后端跑在 `docker-compose` 默认配置下，`web` 服务监听宿主机 `WEB_PORT`（默认 `8080`），此时填 `http://<后端host>:8080/api`；如果你的 `.env` 把 `WEB_PORT` 改成了别的端口（比如 `18000`），就填 `http://<后端host>:18000/api`。
  - 如果不走 `web` 的 nginx，直接连 `api` 容器（`API_PORT`，默认 `8000`），FastAPI 应用本身**没有** `/api` 前缀，这时要填 `http://<后端host>:8000`（不带 `/api`）。
  - 两种情况最终请求路径都应该能命中后端的 `POST /import/offers`。
- **导入 Token `token`**：要和后端「货源配置」（`sources` 配置分类下的 `import_token`）一致，ingest 接口用 `X-Import-Token` 头做鉴权，不一致会 401。
  - 现在前端「货源配置」页（`/settings/sources`，admin 登录后可见）已经直接有「采集令牌（`import_token`）」字段，填一个你自己定的 token 值、保存即可；`import_1688_*_path` 这几个解析路径的 override（`import_1688_list_path`/`import_1688_offer_id_path`/`title_path`/`price_path`/`image_path`/`shop_path`/`detail_url_path`/`sales_path`）在该页的「高级设置」里，同样在页面上直接填。
  - 把「货源配置」页填的同一个 token 值填进扩展 options 的「导入 Token」，两边要一致。
  - 如果不想登录后台页面，也可以用管理员账号拿 JWT 后直接调 `PUT /settings/sources` 写入，作为**可选/备用**途径，例如：
    ```bash
    TOKEN=$(curl -s -X POST http://<后端host>:8080/api/auth/login \
      -d 'username=<管理员账号>&password=<密码>' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
    curl -s -X PUT http://<后端host>:8080/api/settings/sources \
      -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
      -d '{"import_token": "<你要用的token,自己定义即可>"}'
    ```
    注意 `/auth/login` 是 OAuth2 密码模式（`OAuth2PasswordRequestForm`），要用**表单编码**（`-d 'username=...&password=...'`），不能传 JSON body，否则会 422。`PUT /settings/sources` 这一步用的是普通 JSON body，两者编码不同不要混用。
- **匹配子串 `matchSubstr`**：逗号分隔的多个子串，只要拦截到的请求 URL 包含其中任意一个就会被当成命中。默认 `search,offer`，先用默认值试；如果「导入商品」页一直没数据但「采集原始记录」（`GET /import/captures`，管理员可查）里有记录，说明命中的接口不对或响应结构对不上解析路径，按下面「验证」一节调整。
- **关键词 `keyword`**（可选）：只是记录用，会作为 `?keyword=` 拼到 ingest 请求上，方便在后端区分这批数据是搜的什么词，不影响拦截逻辑。

填完点「保存」，`chrome.storage.sync` 落盘即时生效（不需要重新加载页面/扩展，但已经打开的 1688 页面要刷新一下才会重新注入拿到新的 `matchSubstr`）。

## 验证

1. 打开 `1688.com`，正常登录账号。
2. 在搜索框按关键词搜索一次（触发页面自己发出商品列表请求，被 `interceptor.js` 拦到）。
3. 打开后端 Web「导入商品」页（`/imported`，需要 admin 角色），刷新看是否出现刚采集到的商品行（标题/价格/图片/店铺/销量等，来自 `parse_1688_search` 按 `import_1688_*_path` 解析出的字段）。
4. **如果「导入商品」页是空的**：
   - 先确认扩展是否真的发出了请求：`chrome://extensions` 里该扩展点「service worker」打开 DevTools 看 `background.js` 有没有报错；或者直接在 1688 页面 DevTools Network 里筛 `import/offers` 看有没有请求、状态码是什么（401 = token 不对，跨域被拦 = 看下面 CORS 段）。
   - 再看后端「采集原始记录」（`GET /import/captures`，管理员权限；目前后端有接口但前端可能还没做专门页面，可以直接调 API 或用 `GET /import/captures/{id}` 看某一条的 `raw` 字段）：如果这里有记录但 `item_count`/解析出的商品数是 0，说明请求确实拦到了、也传到后端了，但 `parse_1688_search` 按配置的路径在这个 JSON 结构里找不到列表/字段。打开这条 `raw`，对照真实响应结构，去后端「货源配置」把 `import_1688_list_path`（商品列表在 JSON 里的路径，如 `data.offerList`）以及 `import_1688_offer_id_path`/`title_path`/`price_path`/`image_path`/`shop_path`/`detail_url_path`/`sales_path` 这些逐个字段路径改成和真实响应匹配的路径（写法同 `ali1688_offer_list_path`，点号分隔的 JSON 路径），这些字段同样要通过上面提到的 `PUT /settings/sources` 接口写入（前端页面暂未提供表单）。
   - 如果「采集原始记录」里干脆没有任何记录：说明请求没拦到或没发出去，回去检查 `matchSubstr` 是否真的能命中 1688 搜索接口的 URL（在 Network 面板找真正发起搜索的那条 XHR/fetch，看它的 URL 里有没有你配置的子串），必要时把 `matchSubstr` 改成更贴近真实 URL 的片段（比如具体接口路径的一段）。

## CORS 提示

扩展 `background.js` 里的 `fetch` 是从 service worker 发出的，不受 1688 页面本身的同源策略约束，但仍然要过**后端**的 CORS 检查（浏览器按请求发起方 `chrome-extension://<id>` 这个 origin 校验响应头）。本项目后端默认 `cors_origins = ["*"]`（见 `server/app/core/config.py`），PoC 环境下默认就是放开的，一般不用额外配置；如果你的部署把 `cors_origins` 改成了白名单，需要把扩展的 origin（`chrome-extension://<扩展ID>`，ID 在 `chrome://extensions` 详情页能看到）加进去，否则浏览器会在预检/响应阶段拦掉请求（Network 里能看到请求发出去了但报 CORS 错误，`background.js` 里的 `catch (e) {}` 会把这个错误吞掉，所以看不到日志只能靠 Network 面板确认）。

## 安全说明（threat model）

`content.js` 里监听 `window.message` 时只校验了 `e.source === window`（同一窗口），并没有校验消息来源脚本的身份——理论上 1688 页面上的任何脚本（包括页面自身注入的第三方脚本）都能伪造一条带 `__ozonCollector` 标记的 `postMessage` 冒充采集数据。这个信任边界对「PoC、只在自己账号上跑」的场景是可接受的，但如果以后要接不受信任的页面或多人共用环境，需要加一层来源校验（比如校验 payload 结构/签名）再放行。
