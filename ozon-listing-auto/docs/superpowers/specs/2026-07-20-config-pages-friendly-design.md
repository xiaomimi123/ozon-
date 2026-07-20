# 设计文档：配置页小白化（友好标签 + 说明 + 高级折叠 + 条件显隐）

> 日期：2026-07-20。子项目③（三件事：①自动上品✅ → ②货源账号池✅ → ③配置页小白化）。
> 用户决策：全部配置页；选「模拟」时真实字段整块隐藏；定价页只轻改（折 2 个高级项）。

## 1. 背景与现状（已核对代码）

6 个配置页（`web/src/pages/settings/` 与 `web/src/pages/PricingSettings.tsx`），术语/技术字段暴露给运营：
- **LlmSettings**：Provider(mock/openai)、Base URL、Api Key、模型。
- **ImagegenSettings**：Provider(mock/local/openai_compat/http)、Base URL、Api Key、模型、降级顺序、**请求体模板(JSON, 含 {prompt}/{model})**、**响应取图点路径(如 data.0.url)**。
- **CrawlerSettings**：Cookie、代理、超时、最小/最大请求间隔、最大重试。
- **SourcesSettings**：图搜端点、关键词端点、请求方法、**额外请求参数(JSON)**、**额外请求头(JSON)**、**offerList 点路径**。
- **SystemSettings**：上品模式(已中文)、试运行(已中文)、`Category Tree Provider`(仍英文标签, mock/real)。
- **PricingSettings**：已较友好（中文标签 + `shouldUpdate` 条件显示公式）；参数偏多。

所有页共性：`Form layout="vertical"`；密文字段 GET 脱敏、加载时置空；provider 用 `Select`；`putXxx(values)` 保存。**本次纯前端 UI 改造，字段名/值/后端接口不变。**

## 2. 目标与范围

**目标**：让非技术运营也能看懂并配置——中文直白标签 + 每项一句人话说明 + 技术字段折进默认隐藏的「高级设置」 + 选「模拟」时隐藏真实字段。

**范围**：改 6 个页面 UI；新增一个共享 `AdvancedSection` 折叠组件。**不改**：后端、api 封装、字段名、保存 payload 结构、配置存储。

**不做（YAGNI）**：多语言；删除技术字段（抓包仍需，只折叠+加说明）；PricingSettings 大改（仅折 2 项）。

## 3. 共享组件 `AdvancedSection`

`web/src/components/AdvancedSection.tsx`：
```tsx
import { Collapse } from "antd";
import type { ReactNode } from "react";

export default function AdvancedSection({ children }: { children: ReactNode }) {
  return (
    <Collapse
      ghost
      items={[{ key: "adv", label: "高级设置（一般无需修改）", children }]}
      style={{ marginBottom: 8 }}
    />
  );
}
```
- 默认折叠（不设 defaultActiveKey）。所有页复用。折叠内放对应 `Form.Item`（Form.Item 在 Collapse 内仍受同一 Form 管理，值照常提交）。

## 4. 各页改造

**通用做法**：`Select` provider 选项 label 改「模拟（不调用，免费跑通）/ 真实（调用外部）」等（value 不变）；真实字段用 `Form.Item shouldUpdate` 依据 provider 值条件渲染（选模拟时整块不渲染，但**字段仍在 DEFAULTS/表单里**——不渲染不影响已存值提交，因为 setFieldsValue 已注入）。

> 注意：条件不渲染的字段，其表单值仍由 `form` 持有（加载时 setFieldsValue 注入），提交 `form.validateFields`/`onFinish` 的 `values` 仍包含它们，保存 payload 不变。密文字段（api_key 等）加载置空的既有逻辑保留。

### 4.1 LlmSettings
- 标签：Provider→「大模型来源」；Base URL→「接口地址」；Api Key→「密钥」；模型→「模型名称」。
- 选项：`mock`→「模拟（不调用大模型）」、`openai`→「真实（OpenAI 兼容接口）」。
- 常用可见：来源；**当来源=真实时**显「密钥」「模型名称」。
- 高级折叠：「接口地址」（`extra`：默认通义千问 DashScope，一般不用改）。
- 说明：来源 `extra`「模拟仅用于跑通流程、不产生真实文案；真实需填密钥」。

### 4.2 ImagegenSettings
- 标签：Provider→「生图方式」；Base URL→「接口地址」；Api Key→「密钥」；模型→「模型名称」；降级顺序保留名+说明；请求体模板/响应取图路径保留名+更白话说明。
- 选项：`mock`→「模拟（占位图）」、`local`→「本地改图（裁剪/水印，免外部）」、`openai_compat`→「真实·OpenAI 兼容」、`http`→「真实·自定义 HTTP 接口」。
- 常用可见：生图方式；**当方式=openai_compat 或 http 时**显「密钥」「模型名称」。
- 高级折叠：接口地址、降级顺序、请求体模板(JSON)、响应取图路径。请求体模板 `extra`「仅『自定义 HTTP 接口』用：发给接口的 JSON，`{prompt}` 会替换成提示词、`{model}` 替换成模型名」；响应路径 `extra`「仅『自定义 HTTP 接口』用：从返回 JSON 里取图片地址的路径，如 data.0.url」。

### 4.3 CrawlerSettings
- 标签：Cookie 保留 + 白话说明；代理保留 + 说明。
- 常用可见：Cookie（`extra`「在浏览器登录 ozon.ru 后，从开发者工具复制整条 Cookie；留空不改」）、代理（`extra`「可选：走代理访问，降低被风控概率；留空不用」）。
- 高级折叠：超时(秒)、最小请求间隔(秒)、最大请求间隔(秒)、最大重试次数（`extra` 各一句，如「两次请求最短间隔，太快易被封」）。

### 4.4 SourcesSettings
- 标签：图搜端点→「1688 图搜接口地址」；关键词端点→「1688 关键词搜索接口地址」；请求方法保留；额外参数/额外请求头/offerList 路径保留名+白话说明。
- 常用可见：两个接口地址（顶部 `Typography` 说明「这些是 1688 内部接口，需要你从浏览器抓包获取；不确定就先留空，1688 采集暂不可用」）。
- 高级折叠：请求方法、额外请求参数(JSON)、额外请求头(JSON)、offerList 路径（各 `extra` 白话，如 offerList 路径「从返回 JSON 里取商品列表的位置，一般 data.offerList」）。

### 4.5 SystemSettings
- 仅把 `category_tree_provider` 标签「Category Tree Provider」→「类目数据来源」，选项 `mock`→「模拟」、`real`→「真实（抓取 Ozon 真实类目，需爬虫配置 Cookie）」。上品模式/试运行保持。无高级折叠。

### 4.6 PricingSettings（轻改）
- 高级折叠：把「最低售价」「划线价系数」两项折进 `AdvancedSection`（各加一句说明）。其余（定价模式/佣金率/履约费率/汇率/目标毛利率/物流费）保持可见；自定义公式仍按 `mode` 条件显示。

## 5. 测试（每页 Vitest + mock 对应 api）

- 默认渲染：只显常用字段；「高级设置」文案存在且**默认折叠**（高级字段的 label 初始不可见，展开后可见）。
- 条件显隐：LLM/生图选「真实」类 provider 后，「密钥」等真实字段出现；选「模拟」时不显。
- 保存不变：填写后 `putXxx` 被调用、payload 字段名与原先一致（抽查关键字段）。
- 共享组件 `AdvancedSection` 渲染折叠标题。
- 全量 `npm run build` + `vitest run` 通过。

## 6. 验收标准
1. 6 页标签中文直白、每项有说明；provider 选项为「模拟/真实」白话措辞。
2. 每页技术字段折进默认折叠的「高级设置（一般无需修改）」（系统设置无需）。
3. 选「模拟」时不显真实字段；选「真实」显。
4. 保存后端 payload 字段名/值不变（各页既有 api 测试或新测试证明）。
5. 前端 build + vitest 全绿。

## 7. 风险与降级
| 风险 | 应对 |
|---|---|
| 条件不渲染导致字段值丢失/不提交 | 字段值由 `form` 持有（setFieldsValue 注入），不渲染不清值；提交仍带上。抽测保存 payload。 |
| 折叠内 Form.Item 不受表单管理 | antd Collapse 内 Form.Item 仍在同一 Form 上下文，值正常；测试覆盖。 |
| 密文字段脱敏逻辑被破坏 | 保留各页「加载时置空 api_key/cookie」既有逻辑，不动。 |
| provider 值被误改 | 只改 label 文案，Select `value` 不变。 |
