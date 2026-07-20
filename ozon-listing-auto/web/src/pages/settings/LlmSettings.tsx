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
