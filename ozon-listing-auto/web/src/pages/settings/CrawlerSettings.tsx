import { useEffect } from "react";
import { Card, Form, Input, InputNumber, Button, message, Typography } from "antd";
import { getCrawler, putCrawler } from "../../api/crawler";

const DEFAULTS = { cookie: "", proxy: "", timeout: 20, min_delay: 0.3, max_delay: 1.0, max_retries: 4 };

export default function CrawlerSettings() {
  const [form] = Form.useForm();

  useEffect(() => {
    getCrawler().then((d) => form.setFieldsValue({ ...DEFAULTS, ...d, cookie: "", proxy: "" })).catch(() => {});
  }, []);

  const onFinish = async (values: any) => {
    try {
      await putCrawler(values);
      message.success("爬虫配置已保存");
    } catch {
      message.error("保存失败");
    }
  };

  return (
    <Card title="爬虫配置">
      <Typography.Paragraph type="secondary">
        配置采集 Ozon 商品所需的 Cookie / 代理及请求节奏。已保存的 Cookie/代理不会回显(脱敏)，留空则不修改。
      </Typography.Paragraph>
      <Form form={form} layout="vertical" initialValues={DEFAULTS} onFinish={onFinish} style={{ maxWidth: 480 }}>
        <Form.Item name="cookie" label="Cookie" extra="从浏览器 devtools 复制 Cookie 头；留空则不修改">
          <Input.TextArea rows={4} placeholder="留空则不修改" />
        </Form.Item>
        <Form.Item name="proxy" label="代理">
          <Input.Password placeholder="留空则不修改" />
        </Form.Item>
        <Form.Item name="timeout" label="超时时间(秒)" rules={[{ required: true }]}>
          <InputNumber min={1} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item name="min_delay" label="最小请求间隔(秒)" rules={[{ required: true }]}>
          <InputNumber min={0} step={0.1} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item name="max_delay" label="最大请求间隔(秒)" rules={[{ required: true }]}>
          <InputNumber min={0} step={0.1} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item name="max_retries" label="最大重试次数" rules={[{ required: true }]}>
          <InputNumber min={0} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item>
          <Button type="primary" htmlType="submit">保存</Button>
        </Form.Item>
      </Form>
    </Card>
  );
}
