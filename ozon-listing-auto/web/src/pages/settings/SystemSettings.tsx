import { useEffect } from "react";
import { Card, Form, Select, Button, message, Typography } from "antd";
import { getSystem, putSystem } from "../../api/system";

const DEFAULTS = { ozon_seller_provider: "mock" };

export default function SystemSettings() {
  const [form] = Form.useForm();

  useEffect(() => {
    getSystem().then((d) => form.setFieldsValue({ ...DEFAULTS, ...d })).catch(() => {});
  }, []);

  const onFinish = async (values: any) => {
    try {
      await putSystem(values);
      message.success("系统设置已保存");
    } catch {
      message.error("保存失败");
    }
  };

  return (
    <Card title="系统设置">
      <Typography.Paragraph type="secondary">
        切换 Ozon Seller 接入方式。real 需在店铺管理配置真实 Ozon 凭据。
      </Typography.Paragraph>
      <Form form={form} layout="vertical" initialValues={DEFAULTS} onFinish={onFinish} style={{ maxWidth: 480 }}>
        <Form.Item name="ozon_seller_provider" label="Ozon Seller Provider" rules={[{ required: true }]} extra="real 需在店铺管理配置真实 Ozon 凭据">
          <Select
            options={[
              { value: "mock", label: "mock" },
              { value: "real", label: "real" },
            ]}
          />
        </Form.Item>
        <Form.Item>
          <Button type="primary" htmlType="submit">保存</Button>
        </Form.Item>
      </Form>
    </Card>
  );
}
