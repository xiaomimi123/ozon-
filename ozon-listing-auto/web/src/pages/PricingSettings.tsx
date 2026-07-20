import { Card, Form, InputNumber, Select, Input, Button, message, Typography } from "antd";
import { savePricing, PricingParams } from "../api/pricing";
import AdvancedSection from "../components/AdvancedSection";

const DEFAULTS: PricingParams = {
  mode: "builtin",
  commission_rate: 0.15,
  fulfillment_rate: 0.10,
  fx: 13.0,
  target_margin: 0.20,
  logistics: 5.0,
  min_price: 0.0,
  strike_coeff: 1.3,
  formula: "",
};

export default function PricingSettings() {
  const [form] = Form.useForm();

  const onFinish = async (values: PricingParams) => {
    try {
      await savePricing(values);
      message.success("定价参数已保存");
    } catch (e) {
      message.error("保存失败");
    }
  };

  return (
    <Card title="定价设置">
      <Typography.Paragraph type="secondary">
        内置反推使用公式：售价 = 到手成本 / (1 - 目标毛利率 - 佣金率 - 履约费率) × 汇率。仅需填写要覆盖的参数，未填写项使用系统默认值。
        出于安全考虑，已保存的参数不会回显，请每次按需重新填写并保存。
      </Typography.Paragraph>
      <Form form={form} layout="vertical" initialValues={DEFAULTS} onFinish={onFinish} style={{ maxWidth: 480 }}>
        <Form.Item name="mode" label="定价模式" rules={[{ required: true }]}>
          <Select
            options={[
              { value: "builtin", label: "内置反推" },
              { value: "formula", label: "自定义公式" },
            ]}
          />
        </Form.Item>
        <Form.Item name="commission_rate" label="佣金率" rules={[{ required: true }]}>
          <InputNumber style={{ width: "100%" }} step={0.01} min={0} max={1} />
        </Form.Item>
        <Form.Item name="fulfillment_rate" label="履约费率" rules={[{ required: true }]}>
          <InputNumber style={{ width: "100%" }} step={0.01} min={0} max={1} />
        </Form.Item>
        <Form.Item name="fx" label="汇率" rules={[{ required: true }]}>
          <InputNumber style={{ width: "100%" }} step={0.1} min={0} />
        </Form.Item>
        <Form.Item name="target_margin" label="目标毛利率" rules={[{ required: true }]}>
          <InputNumber style={{ width: "100%" }} step={0.01} min={0} max={1} />
        </Form.Item>
        <Form.Item name="logistics" label="物流费" rules={[{ required: true }]}>
          <InputNumber style={{ width: "100%" }} step={0.1} min={0} />
        </Form.Item>
        <AdvancedSection>
          <Form.Item name="min_price" label="最低售价" rules={[{ required: true }]} extra="低于此价不上架（保护下限）">
            <InputNumber style={{ width: "100%" }} step={0.1} min={0} />
          </Form.Item>
          <Form.Item name="strike_coeff" label="划线价系数" rules={[{ required: true }]} extra="划线价=售价×系数，用于展示折扣">
            <InputNumber style={{ width: "100%" }} step={0.01} min={0} />
          </Form.Item>
        </AdvancedSection>
        <Form.Item shouldUpdate={(prev, cur) => prev.mode !== cur.mode} noStyle>
          {({ getFieldValue }) =>
            getFieldValue("mode") === "formula" ? (
              <Form.Item
                name="formula"
                label="自定义公式"
                extra="可用变量：cost / logistics / commission_rate / fulfillment_rate / fx / weight / target_margin / min_price"
              >
                <Input.TextArea rows={3} placeholder="例如：(cost + logistics) / (1 - target_margin - commission_rate - fulfillment_rate) * fx" />
              </Form.Item>
            ) : null
          }
        </Form.Item>
        <Form.Item>
          <Button type="primary" htmlType="submit">保存</Button>
        </Form.Item>
      </Form>
    </Card>
  );
}
