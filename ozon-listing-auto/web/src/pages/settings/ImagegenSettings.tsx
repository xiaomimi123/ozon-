import { useEffect } from "react";
import { Card, Form, Input, Select, Button, message, Typography } from "antd";
import { getImagegen, putImagegen } from "../../api/imagegen";

const DEFAULTS = { provider: "mock", img_base_url: "", img_api_key: "", img_model: "", fallback: "" };

export default function ImagegenSettings() {
  const [form] = Form.useForm();

  useEffect(() => {
    getImagegen().then((d) => form.setFieldsValue({ ...DEFAULTS, ...d, img_api_key: "" })).catch(() => {});
  }, []);

  const onFinish = async (values: any) => {
    try {
      await putImagegen(values);
      message.success("AI 生图配置已保存");
    } catch {
      message.error("保存失败");
    }
  };

  return (
    <Card title="AI 生图配置">
      <Typography.Paragraph type="secondary">
        配置改图/生图 provider 及降级顺序。已保存的 Api-Key 不会回显(脱敏)，如需更换请重新填写。
      </Typography.Paragraph>
      <Form form={form} layout="vertical" initialValues={DEFAULTS} onFinish={onFinish} style={{ maxWidth: 480 }}>
        <Form.Item name="provider" label="Provider" rules={[{ required: true }]}>
          <Select
            options={[
              { value: "mock", label: "mock" },
              { value: "local", label: "local" },
              { value: "openai_compat", label: "openai_compat" },
              { value: "http", label: "http" },
            ]}
          />
        </Form.Item>
        <Form.Item name="img_base_url" label="Base URL">
          <Input placeholder="https://..." />
        </Form.Item>
        <Form.Item name="img_api_key" label="Api Key">
          <Input.Password placeholder="留空则不更改" />
        </Form.Item>
        <Form.Item name="img_model" label="模型">
          <Input placeholder="例如 gpt-image-1" />
        </Form.Item>
        <Form.Item name="fallback" label="降级顺序" extra="逗号分隔，例如 local,mock">
          <Input placeholder="local,mock" />
        </Form.Item>
        <Form.Item>
          <Button type="primary" htmlType="submit">保存</Button>
        </Form.Item>
      </Form>
    </Card>
  );
}
