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
  const onFinish = async () => {
    try { await putImagegen(form.getFieldsValue(true)); message.success("AI 生图配置已保存"); }
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
