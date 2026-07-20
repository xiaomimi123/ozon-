# 配置页小白化 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 6 个配置页对非技术运营友好：中文直白标签 + 每项一句说明 + 技术字段折进默认折叠的「高级设置」 + 选「模拟」时隐藏真实字段；后端/字段名/保存 payload 一律不变。

**Architecture:** 新增共享折叠组件 `AdvancedSection`；逐页把技术字段搬进它、真实凭证字段按 provider 条件渲染、标签与 provider 选项改白话。纯前端 UI 改造。

**Tech Stack:** React 18 + TS + Ant Design 5 + Vitest。

## Global Constraints

- **字段名、Select 的 `value`、保存 payload 结构一律不变**——只改 `label`/`extra`/`tooltip`/选项文案/可见性/排版。后端、`api/*.ts` 不动。
- **值不丢**：`AdvancedSection` 的 Collapse item 设 `forceRender: true`（折叠内 Form.Item 始终挂载→始终提交）。provider 条件字段用 `shouldUpdate` render-prop 条件渲染；依赖 antd Form **默认 `preserve: true`**（卸载字段仍保留值并提交）——**不要设 `preserve={false}`**。
- 各页**保留既有脱敏逻辑**：加载时把 `llm_api_key`/`img_api_key`/`cookie`/`proxy` 置空（留空不覆盖）。
- provider 选项 label 用白话「模拟…/真实…」，`value` 保持 `mock/openai/local/openai_compat/http/real` 不变。
- 每页每步保证 `cd web && npx vitest run <page>` 通过；全部完成后 `npm run build` 通过。
- 测试断言聚焦：常用字段可见、「高级设置（一般无需修改）」折叠标题存在、provider=真实类时真实字段出现/模拟时不出现、保存调用 `putXxx`（抽查关键字段名不变）。不强断言 jsdom 里折叠内容的可见性。

---

### Task 1: 共享组件 AdvancedSection

**Files:**
- Create: `web/src/components/AdvancedSection.tsx`
- Test: `web/src/components/AdvancedSection.test.tsx`

**Interfaces:**
- Produces: `export default function AdvancedSection({ children }: { children: ReactNode })` —— 默认折叠的 antd Collapse（ghost），标题「高级设置（一般无需修改）」，item `forceRender: true`。

- [ ] **Step 1: 写失败测试**

```tsx
// web/src/components/AdvancedSection.test.tsx
import { render, screen } from "@testing-library/react";
import AdvancedSection from "./AdvancedSection";

test("渲染高级设置折叠标题且子项内容默认不展开可见", () => {
  render(<AdvancedSection><div>高级字段X</div></AdvancedSection>);
  expect(screen.getByText("高级设置（一般无需修改）")).toBeInTheDocument();
  // forceRender 下子项在 DOM 中（折叠隐藏），标题一定在
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd web && npx vitest run src/components/AdvancedSection -q`
Expected: FAIL（组件不存在）

- [ ] **Step 3: 实现**

```tsx
// web/src/components/AdvancedSection.tsx
import { Collapse } from "antd";
import type { ReactNode } from "react";

export default function AdvancedSection({ children }: { children: ReactNode }) {
  return (
    <Collapse
      ghost
      style={{ marginBottom: 8 }}
      items={[{ key: "adv", label: "高级设置（一般无需修改）", forceRender: true, children }]}
    />
  );
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd web && npx vitest run src/components/AdvancedSection -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add web/src/components/AdvancedSection.tsx web/src/components/AdvancedSection.test.tsx
git commit -m "feat(web): 共享 AdvancedSection 折叠组件(默认收起)"
```

---

### Task 2: LLM 配置 + AI 生图 配置 小白化

**Files:**
- Modify: `web/src/pages/settings/LlmSettings.tsx`
- Modify: `web/src/pages/settings/ImagegenSettings.tsx`
- Test: `web/src/pages/settings/LlmSettings.test.tsx`、`web/src/pages/settings/ImagegenSettings.test.tsx`（无则建）

**Interfaces:**
- Consumes: `AdvancedSection`（Task 1）。api/字段名不变。

- [ ] **Step 1: 写失败测试（两页）**

```tsx
// LlmSettings.test.tsx —— mock ../../api/llm，仿现有测试
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
vi.mock("../../api/llm", () => ({ getLlm: vi.fn(() => Promise.resolve({ llm_provider: "mock" })), putLlm: vi.fn() }));
import LlmSettings from "./LlmSettings";
test("显示白话标签与高级折叠，模拟时不显密钥", async () => {
  render(<LlmSettings />);
  expect(await screen.findByText("大模型来源")).toBeInTheDocument();
  expect(screen.getByText("高级设置（一般无需修改）")).toBeInTheDocument();
  expect(screen.queryByText("密钥")).toBeNull();  // provider=mock 时真实字段不渲染
});
```
```tsx
// ImagegenSettings.test.tsx
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
vi.mock("../../api/imagegen", () => ({ getImagegen: vi.fn(() => Promise.resolve({ provider: "mock" })), putImagegen: vi.fn() }));
import ImagegenSettings from "./ImagegenSettings";
test("显示白话标签与高级折叠", async () => {
  render(<ImagegenSettings />);
  expect(await screen.findByText("生图方式")).toBeInTheDocument();
  expect(screen.getByText("高级设置（一般无需修改）")).toBeInTheDocument();
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd web && npx vitest run src/pages/settings/LlmSettings src/pages/settings/ImagegenSettings -q`
Expected: FAIL

- [ ] **Step 3: 实现 LlmSettings.tsx（完整替换）**

```tsx
import { useEffect } from "react";
import { Card, Form, Input, Select, Button, message, Typography } from "antd";
import { getLlm, putLlm } from "../../api/llm";
import AdvancedSection from "../../components/AdvancedSection";

const DEFAULTS = { llm_provider: "mock", llm_base_url: "", llm_api_key: "", llm_model: "" };

export default function LlmSettings() {
  const [form] = Form.useForm();
  useEffect(() => {
    getLlm().then((d) => form.setFieldsValue({ ...DEFAULTS, ...d, llm_api_key: "" })).catch(() => {});
  }, []);
  const onFinish = async (values: any) => {
    try { await putLlm(values); message.success("LLM 配置已保存"); }
    catch { message.error("保存失败"); }
  };
  return (
    <Card title="LLM 配置">
      <Typography.Paragraph type="secondary">
        用于生成商品标题/描述、类目建议等。「模拟」不调用大模型、只跑通流程；「真实」需填密钥。已保存的密钥不回显，换密钥时重新填写。
      </Typography.Paragraph>
      <Form form={form} layout="vertical" initialValues={DEFAULTS} onFinish={onFinish} style={{ maxWidth: 480 }}>
        <Form.Item name="llm_provider" label="大模型来源" rules={[{ required: true }]}
          extra="模拟：不产生真实文案、免费跑通；真实：调用 OpenAI 兼容大模型">
          <Select options={[
            { value: "mock", label: "模拟（不调用大模型）" },
            { value: "openai", label: "真实（OpenAI 兼容接口）" },
          ]} />
        </Form.Item>
        <Form.Item noStyle shouldUpdate={(p, c) => p.llm_provider !== c.llm_provider}>
          {({ getFieldValue }) => getFieldValue("llm_provider") === "openai" && (
            <>
              <Form.Item name="llm_api_key" label="密钥" extra="大模型服务的 API Key；留空则不修改">
                <Input.Password placeholder="留空则不更改" />
              </Form.Item>
              <Form.Item name="llm_model" label="模型名称" extra="例如 qwen-plus、gpt-4o-mini">
                <Input placeholder="例如 qwen-plus" />
              </Form.Item>
            </>
          )}
        </Form.Item>
        <AdvancedSection>
          <Form.Item name="llm_base_url" label="接口地址" extra="默认通义千问 DashScope，一般无需修改">
            <Input placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1" />
          </Form.Item>
        </AdvancedSection>
        <Form.Item>
          <Button type="primary" htmlType="submit">保存</Button>
        </Form.Item>
      </Form>
    </Card>
  );
}
```

- [ ] **Step 4: 实现 ImagegenSettings.tsx（完整替换）**

```tsx
import { useEffect } from "react";
import { Card, Form, Input, Select, Button, message, Typography } from "antd";
import { getImagegen, putImagegen } from "../../api/imagegen";
import AdvancedSection from "../../components/AdvancedSection";

const DEFAULTS = {
  provider: "mock", img_base_url: "", img_api_key: "", img_model: "",
  fallback: "", img_request_template: "", img_response_path: "",
};

export default function ImagegenSettings() {
  const [form] = Form.useForm();
  useEffect(() => {
    getImagegen().then((d) => form.setFieldsValue({ ...DEFAULTS, ...d, img_api_key: "" })).catch(() => {});
  }, []);
  const onFinish = async (values: any) => {
    try { await putImagegen(values); message.success("AI 生图配置已保存"); }
    catch { message.error("保存失败"); }
  };
  const isReal = (p: string) => p === "openai_compat" || p === "http";
  return (
    <Card title="AI 生图配置">
      <Typography.Paragraph type="secondary">
        用于生成/修改商品图。「模拟」出占位图；「本地改图」只做裁剪/水印、无需外部服务；「真实」调用外部生图接口。已保存的密钥不回显。
      </Typography.Paragraph>
      <Form form={form} layout="vertical" initialValues={DEFAULTS} onFinish={onFinish} style={{ maxWidth: 480 }}>
        <Form.Item name="provider" label="生图方式" rules={[{ required: true }]}
          extra="模拟/本地无需密钥；真实类需填密钥与模型">
          <Select options={[
            { value: "mock", label: "模拟（占位图）" },
            { value: "local", label: "本地改图（裁剪/水印，免外部）" },
            { value: "openai_compat", label: "真实·OpenAI 兼容" },
            { value: "http", label: "真实·自定义 HTTP 接口" },
          ]} />
        </Form.Item>
        <Form.Item noStyle shouldUpdate={(p, c) => p.provider !== c.provider}>
          {({ getFieldValue }) => isReal(getFieldValue("provider")) && (
            <>
              <Form.Item name="img_api_key" label="密钥" extra="生图服务的 API Key；留空则不修改">
                <Input.Password placeholder="留空则不更改" />
              </Form.Item>
              <Form.Item name="img_model" label="模型名称" extra="例如 gpt-image-1">
                <Input placeholder="例如 gpt-image-1" />
              </Form.Item>
            </>
          )}
        </Form.Item>
        <AdvancedSection>
          <Form.Item name="img_base_url" label="接口地址" extra="真实类生图服务的接口地址">
            <Input placeholder="https://..." />
          </Form.Item>
          <Form.Item name="fallback" label="降级顺序" extra="某方式失败时依次尝试，逗号分隔，例如 local,mock">
            <Input placeholder="local,mock" />
          </Form.Item>
          <Form.Item name="img_request_template" label="请求体模板（JSON）"
            extra="仅『自定义 HTTP 接口』用：发给接口的 JSON，{prompt} 会替换成提示词、{model} 替换成模型名">
            <Input.TextArea placeholder='{"prompt": "{prompt}", "model": "{model}"}' rows={3} />
          </Form.Item>
          <Form.Item name="img_response_path" label="响应取图路径"
            extra="仅『自定义 HTTP 接口』用：从返回 JSON 里取图片地址的位置，如 data.0.url">
            <Input placeholder="data.0.url" />
          </Form.Item>
        </AdvancedSection>
        <Form.Item>
          <Button type="primary" htmlType="submit">保存</Button>
        </Form.Item>
      </Form>
    </Card>
  );
}
```

- [ ] **Step 5: 运行测试**

Run: `cd web && npx vitest run src/pages/settings/LlmSettings src/pages/settings/ImagegenSettings -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add web/src/pages/settings/LlmSettings.tsx web/src/pages/settings/ImagegenSettings.tsx web/src/pages/settings/LlmSettings.test.tsx web/src/pages/settings/ImagegenSettings.test.tsx
git commit -m "feat(web): LLM/生图配置小白化(白话标签+高级折叠+条件显真实字段)"
```

---

### Task 3: 爬虫配置 + 货源配置 小白化

**Files:**
- Modify: `web/src/pages/settings/CrawlerSettings.tsx`
- Modify: `web/src/pages/settings/SourcesSettings.tsx`
- Test: `web/src/pages/settings/CrawlerSettings.test.tsx`、`web/src/pages/settings/SourcesSettings.test.tsx`

**Interfaces:**
- Consumes: `AdvancedSection`。api/字段名不变。

- [ ] **Step 1: 写失败测试（两页）**

```tsx
// CrawlerSettings.test.tsx
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
vi.mock("../../api/crawler", () => ({ getCrawler: vi.fn(() => Promise.resolve({})), putCrawler: vi.fn() }));
import CrawlerSettings from "./CrawlerSettings";
test("常用字段可见+高级折叠存在", async () => {
  render(<CrawlerSettings />);
  expect(await screen.findByText("Cookie")).toBeInTheDocument();
  expect(screen.getByText("高级设置（一般无需修改）")).toBeInTheDocument();
});
```
```tsx
// SourcesSettings.test.tsx
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
vi.mock("../../api/sources", () => ({ getSources: vi.fn(() => Promise.resolve({})), putSources: vi.fn() }));
import SourcesSettings from "./SourcesSettings";
test("端点可见+高级折叠存在", async () => {
  render(<SourcesSettings />);
  expect(await screen.findByText("1688 图搜接口地址")).toBeInTheDocument();
  expect(screen.getByText("高级设置（一般无需修改）")).toBeInTheDocument();
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd web && npx vitest run src/pages/settings/CrawlerSettings src/pages/settings/SourcesSettings -q`
Expected: FAIL

- [ ] **Step 3: 实现 CrawlerSettings.tsx（完整替换）**

```tsx
import { useEffect } from "react";
import { Card, Form, Input, InputNumber, Button, message, Typography } from "antd";
import { getCrawler, putCrawler } from "../../api/crawler";
import AdvancedSection from "../../components/AdvancedSection";

const DEFAULTS = { cookie: "", proxy: "", timeout: 20, min_delay: 0.3, max_delay: 1.0, max_retries: 4 };

export default function CrawlerSettings() {
  const [form] = Form.useForm();
  useEffect(() => {
    getCrawler().then((d) => form.setFieldsValue({ ...DEFAULTS, ...d, cookie: "", proxy: "" })).catch(() => {});
  }, []);
  const onFinish = async (values: any) => {
    try { await putCrawler(values); message.success("爬虫配置已保存"); }
    catch { message.error("保存失败"); }
  };
  return (
    <Card title="爬虫配置">
      <Typography.Paragraph type="secondary">
        采集 Ozon 商品所需的登录 Cookie 与代理。已保存的 Cookie/代理不回显，留空则不修改。
      </Typography.Paragraph>
      <Form form={form} layout="vertical" initialValues={DEFAULTS} onFinish={onFinish} style={{ maxWidth: 480 }}>
        <Form.Item name="cookie" label="Cookie" extra="在浏览器登录 ozon.ru 后，从开发者工具复制整条 Cookie；留空则不修改">
          <Input.TextArea rows={4} placeholder="留空则不修改" />
        </Form.Item>
        <Form.Item name="proxy" label="代理" extra="可选：通过代理访问以降低被风控概率；留空则不使用">
          <Input.Password placeholder="留空则不修改" />
        </Form.Item>
        <AdvancedSection>
          <Form.Item name="timeout" label="超时时间(秒)" rules={[{ required: true }]} extra="单次请求最长等待时间">
            <InputNumber min={1} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="min_delay" label="最小请求间隔(秒)" rules={[{ required: true }]} extra="两次请求最短间隔，太快易被封">
            <InputNumber min={0} step={0.1} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="max_delay" label="最大请求间隔(秒)" rules={[{ required: true }]} extra="两次请求最长间隔（随机取值上限）">
            <InputNumber min={0} step={0.1} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="max_retries" label="最大重试次数" rules={[{ required: true }]} extra="被拦截时的自动重试次数">
            <InputNumber min={0} style={{ width: "100%" }} />
          </Form.Item>
        </AdvancedSection>
        <Form.Item>
          <Button type="primary" htmlType="submit">保存</Button>
        </Form.Item>
      </Form>
    </Card>
  );
}
```

- [ ] **Step 4: 实现 SourcesSettings.tsx（完整替换）**

```tsx
import { useEffect } from "react";
import { Card, Form, Input, Select, Button, message, Typography } from "antd";
import { getSources, putSources } from "../../api/sources";
import AdvancedSection from "../../components/AdvancedSection";

const DEFAULTS = {
  ali1688_image_search_url: "", ali1688_keyword_search_url: "", ali1688_method: "GET",
  ali1688_extra_params: "", ali1688_extra_headers: "", ali1688_offer_list_path: "data.offerList",
};

export default function SourcesSettings() {
  const [form] = Form.useForm();
  useEffect(() => {
    getSources().then((d) => form.setFieldsValue({ ...DEFAULTS, ...d })).catch(() => {});
  }, []);
  const onFinish = async (values: any) => {
    try { await putSources(values); message.success("货源配置已保存"); }
    catch { message.error("保存失败"); }
  };
  return (
    <Card title="货源配置">
      <Typography.Paragraph type="secondary">
        1688 采集用的接口地址。这些是 1688 内部接口，需要你从浏览器抓包获取；不确定就先留空，1688 采集暂不可用。登录 Cookie 请在「货源账号」页填写，本页不存 Cookie。
      </Typography.Paragraph>
      <Form form={form} layout="vertical" initialValues={DEFAULTS} onFinish={onFinish} style={{ maxWidth: 480 }}>
        <Form.Item name="ali1688_image_search_url" label="1688 图搜接口地址" extra="拍立淘以图搜图的接口地址，从浏览器抓包获取">
          <Input placeholder="https://h5api.m.1688.com/..." />
        </Form.Item>
        <Form.Item name="ali1688_keyword_search_url" label="1688 关键词搜索接口地址" extra="按关键词搜索的接口地址，从浏览器抓包获取">
          <Input placeholder="https://..." />
        </Form.Item>
        <AdvancedSection>
          <Form.Item name="ali1688_method" label="请求方法" rules={[{ required: true }]} extra="接口是 GET 还是 POST，看抓包">
            <Select options={[{ value: "GET", label: "GET" }, { value: "POST", label: "POST" }]} />
          </Form.Item>
          <Form.Item name="ali1688_extra_params" label="额外请求参数（JSON）" extra="签名等额外参数，JSON 对象字符串，例如 {&quot;sign&quot;: &quot;...&quot;}">
            <Input.TextArea placeholder='{"sign": "..."}' rows={3} />
          </Form.Item>
          <Form.Item name="ali1688_extra_headers" label="额外请求头（JSON）" extra="额外请求头，JSON 对象字符串，例如 {&quot;x-h5-req&quot;: &quot;...&quot;}">
            <Input.TextArea placeholder='{"x-h5-req": "..."}' rows={3} />
          </Form.Item>
          <Form.Item name="ali1688_offer_list_path" label="响应商品列表路径" extra="从返回 JSON 里取商品列表的位置，一般 data.offerList">
            <Input placeholder="data.offerList" />
          </Form.Item>
        </AdvancedSection>
        <Form.Item>
          <Button type="primary" htmlType="submit">保存</Button>
        </Form.Item>
      </Form>
    </Card>
  );
}
```

- [ ] **Step 5: 运行测试**

Run: `cd web && npx vitest run src/pages/settings/CrawlerSettings src/pages/settings/SourcesSettings -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add web/src/pages/settings/CrawlerSettings.tsx web/src/pages/settings/SourcesSettings.tsx web/src/pages/settings/CrawlerSettings.test.tsx web/src/pages/settings/SourcesSettings.test.tsx
git commit -m "feat(web): 爬虫/货源配置小白化(白话标签+说明+高级折叠)"
```

---

### Task 4: 系统设置（类目来源标签）+ 定价设置（折叠 2 项）

**Files:**
- Modify: `web/src/pages/settings/SystemSettings.tsx`
- Modify: `web/src/pages/PricingSettings.tsx`
- Test: `web/src/pages/settings/SystemSettings.test.tsx`（已存在，追加断言）、`web/src/pages/PricingSettings.test.tsx`

**Interfaces:**
- Consumes: `AdvancedSection`（Pricing 用）。api/字段名不变。

- [ ] **Step 1: 写失败测试**

```tsx
// SystemSettings.test.tsx —— 追加：类目来源中文标签
// （现有文件已 mock ../../api/system；在其中追加）
test("类目数据来源中文标签", async () => {
  render(<SystemSettings />);
  expect(await screen.findByText("类目数据来源")).toBeInTheDocument();
});
```
```tsx
// PricingSettings.test.tsx
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
vi.mock("../api/pricing", () => ({ savePricing: vi.fn(), PricingParams: {} }));
import PricingSettings from "./PricingSettings";
test("常用项可见+高级折叠存在", async () => {
  render(<PricingSettings />);
  expect(await screen.findByText("定价模式")).toBeInTheDocument();
  expect(screen.getByText("高级设置（一般无需修改）")).toBeInTheDocument();
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd web && npx vitest run src/pages/settings/SystemSettings src/pages/PricingSettings -q`
Expected: FAIL

- [ ] **Step 3: 改 SystemSettings.tsx（仅 category_tree_provider 那一项）**

把 `category_tree_provider` 的 `Form.Item` 替换为：
```tsx
        <Form.Item name="category_tree_provider" label="类目数据来源" rules={[{ required: true }]}
          extra="真实需在爬虫配置填 Cookie/代理">
          <Select options={[
            { value: "mock", label: "模拟" },
            { value: "real", label: "真实（抓取 Ozon 真实类目）" },
          ]} />
        </Form.Item>
```
（上品模式/试运行/其余不动。）

- [ ] **Step 4: 改 PricingSettings.tsx（折叠 2 项）**

顶部 `import AdvancedSection from "../components/AdvancedSection";`。把「最低售价」`min_price` 与「划线价系数」`strike_coeff` 两个 `Form.Item` 从主表单移入 `<AdvancedSection>...</AdvancedSection>`（放在「物流费」之后、公式条件项之前），并给两项加 `extra`：
```tsx
        <AdvancedSection>
          <Form.Item name="min_price" label="最低售价" rules={[{ required: true }]} extra="低于此价不上架（保护下限）">
            <InputNumber style={{ width: "100%" }} step={0.1} min={0} />
          </Form.Item>
          <Form.Item name="strike_coeff" label="划线价系数" rules={[{ required: true }]} extra="划线价=售价×系数，用于展示折扣">
            <InputNumber style={{ width: "100%" }} step={0.01} min={0} />
          </Form.Item>
        </AdvancedSection>
```
（其余项、`mode` 条件公式项、DEFAULTS、onFinish 不动。）

- [ ] **Step 5: 运行测试 + 全量 build**

Run: `cd web && npx vitest run src/pages/settings/SystemSettings src/pages/PricingSettings -q && npm run build`
Expected: PASS + build 成功

- [ ] **Step 6: 提交**

```bash
git add web/src/pages/settings/SystemSettings.tsx web/src/pages/PricingSettings.tsx web/src/pages/settings/SystemSettings.test.tsx web/src/pages/PricingSettings.test.tsx
git commit -m "feat(web): 系统设置类目来源中文化 + 定价高级项折叠"
```

---

## 收尾（全部任务后）
- 全量 `cd web && npx vitest run` + `npm run build` 通过。
- README 若有配置页说明，按需微调（本次纯 UI，按比例投入，可不改）。
- 重建 docker web：`WEB_PORT=18080 DB_PORT=15432 REDIS_PORT=16379 API_PORT=18000 docker compose up -d --build web`。

## 自查
- 覆盖 spec：AdvancedSection(T1)、LLM+生图(T2)、爬虫+货源(T3)、系统+定价(T4)——6 页 + 组件全覆盖。
- 字段名/value/payload 不变：各页只改 label/extra/选项文案/可见性；DEFAULTS 与 onFinish 保持。
- 值不丢：AdvancedSection `forceRender:true`；条件字段靠 antd 默认 `preserve:true`；不设 `preserve={false}`。
- 无占位符：各页完整代码给出。
