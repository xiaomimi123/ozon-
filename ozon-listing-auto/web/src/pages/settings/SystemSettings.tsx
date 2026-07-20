import { useEffect } from "react";
import { Card, Form, Select, Switch, Button, message, Typography } from "antd";
import { getSystem, putSystem } from "../../api/system";

const DEFAULTS = { ozon_seller_provider: "mock", category_tree_provider: "mock", ozon_publish_dry_run: true };

export default function SystemSettings() {
  const [form] = Form.useForm();

  useEffect(() => {
    getSystem()
      .then((d) =>
        form.setFieldsValue({
          ...DEFAULTS,
          ...d,
          ozon_publish_dry_run: d.ozon_publish_dry_run !== "false",
        })
      )
      .catch(() => {});
  }, []);

  const onFinish = async (values: any) => {
    try {
      await putSystem({ ...values, ozon_publish_dry_run: values.ozon_publish_dry_run ? "true" : "false" });
      message.success("系统设置已保存");
    } catch {
      message.error("保存失败");
    }
  };

  return (
    <Card title="系统设置">
      <Typography.Paragraph type="secondary">
        切换 Ozon Seller 接入方式与类目树来源。real 需分别在店铺管理 / 爬虫配置填真实凭据。
      </Typography.Paragraph>
      <Form form={form} layout="vertical" initialValues={DEFAULTS} onFinish={onFinish} style={{ maxWidth: 480 }}>
        <Form.Item
          name="ozon_seller_provider"
          label="上品模式"
          rules={[{ required: true }]}
          extra="real 需在店铺管理配置真实 Ozon 凭据"
          tooltip="真实模式会调用 Ozon Seller API 真正上品"
        >
          <Select
            options={[
              { value: "mock", label: "模拟（不真发）" },
              { value: "real", label: "真实（调用 Ozon）" },
            ]}
          />
        </Form.Item>
        <Form.Item
          name="ozon_publish_dry_run"
          label="试运行(dry-run)"
          valuePropName="checked"
          tooltip="真实模式下先只构造请求、不真正提交；确认无误后再关闭真发"
        >
          <Switch />
        </Form.Item>
        <Form.Item name="category_tree_provider" label="类目数据来源" rules={[{ required: true }]}
          extra="真实需在爬虫配置填 Cookie/代理">
          <Select options={[
            { value: "mock", label: "模拟" },
            { value: "real", label: "真实（抓取 Ozon 真实类目）" },
          ]} />
        </Form.Item>
        <Form.Item>
          <Button type="primary" htmlType="submit">保存</Button>
        </Form.Item>
      </Form>
    </Card>
  );
}
