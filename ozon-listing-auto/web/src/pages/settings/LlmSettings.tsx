import { useEffect } from "react";
import { Card, Form, Input, Select, Button, message, Typography } from "antd";
import { getLlm, putLlm } from "../../api/llm";

const DEFAULTS = { llm_provider: "mock", llm_base_url: "", llm_api_key: "", llm_model: "" };

export default function LlmSettings() {
  const [form] = Form.useForm();

  useEffect(() => {
    getLlm().then((d) => form.setFieldsValue({ ...DEFAULTS, ...d, llm_api_key: "" })).catch(() => {});
  }, []);

  const onFinish = async (values: any) => {
    try {
      await putLlm(values);
      message.success("LLM 配置已保存");
    } catch {
      message.error("保存失败");
    }
  };

  return (
    <Card title="LLM 配置">
      <Typography.Paragraph type="secondary">
        默认通义千问 DashScope；api_key 留空不修改。已保存的 Api-Key 不会回显(脱敏)，如需更换请重新填写。
      </Typography.Paragraph>
      <Form form={form} layout="vertical" initialValues={DEFAULTS} onFinish={onFinish} style={{ maxWidth: 480 }}>
        <Form.Item name="llm_provider" label="Provider" rules={[{ required: true }]}>
          <Select
            options={[
              { value: "mock", label: "mock" },
              { value: "openai", label: "openai" },
            ]}
          />
        </Form.Item>
        <Form.Item name="llm_base_url" label="Base URL">
          <Input placeholder="https://..." />
        </Form.Item>
        <Form.Item name="llm_api_key" label="Api Key">
          <Input.Password placeholder="留空则不更改" />
        </Form.Item>
        <Form.Item name="llm_model" label="模型">
          <Input placeholder="例如 qwen-plus" />
        </Form.Item>
        <Form.Item>
          <Button type="primary" htmlType="submit">保存</Button>
        </Form.Item>
      </Form>
    </Card>
  );
}
