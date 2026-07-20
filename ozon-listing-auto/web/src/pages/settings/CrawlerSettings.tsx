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
