import { useEffect } from "react";
import { Card, Form, Input, Select, Button, message, Typography } from "antd";
import { getSources, putSources } from "../../api/sources";

const DEFAULTS = {
  ali1688_image_search_url: "",
  ali1688_keyword_search_url: "",
  ali1688_method: "GET",
  ali1688_extra_params: "",
  ali1688_extra_headers: "",
  ali1688_offer_list_path: "data.offerList",
};

export default function SourcesSettings() {
  const [form] = Form.useForm();

  useEffect(() => {
    getSources().then((d) => form.setFieldsValue({ ...DEFAULTS, ...d })).catch(() => {});
  }, []);

  const onFinish = async (values: any) => {
    try {
      await putSources(values);
      message.success("货源配置已保存");
    } catch {
      message.error("保存失败");
    }
  };

  return (
    <Card title="货源配置">
      <Typography.Paragraph type="secondary">
        1688 拍立淘图搜端点/签名参数(需从浏览器抓包填写)/响应 offerList 点路径；cookie 请在「货源账号池」填写，本页不存 cookie。
      </Typography.Paragraph>
      <Form form={form} layout="vertical" initialValues={DEFAULTS} onFinish={onFinish} style={{ maxWidth: 480 }}>
        <Form.Item name="ali1688_image_search_url" label="图搜端点(image_search_url)" extra="拍立淘以图搜图的真实接口地址，从浏览器抓包获取">
          <Input placeholder="https://h5api.m.1688.com/..." />
        </Form.Item>
        <Form.Item name="ali1688_keyword_search_url" label="关键词搜索端点(keyword_search_url)">
          <Input placeholder="https://..." />
        </Form.Item>
        <Form.Item name="ali1688_method" label="请求方法" rules={[{ required: true }]}>
          <Select
            options={[
              { value: "GET", label: "GET" },
              { value: "POST", label: "POST" },
            ]}
          />
        </Form.Item>
        <Form.Item
          name="ali1688_extra_params"
          label="额外请求参数(JSON)"
          extra="签名等额外参数，JSON 对象字符串，例如 {&quot;sign&quot;: &quot;...&quot;}"
        >
          <Input.TextArea placeholder='{"sign": "..."}' rows={3} />
        </Form.Item>
        <Form.Item
          name="ali1688_extra_headers"
          label="额外请求头(JSON)"
          extra="JSON 对象字符串，例如 {&quot;x-h5-req&quot;: &quot;...&quot;}"
        >
          <Input.TextArea placeholder='{"x-h5-req": "..."}' rows={3} />
        </Form.Item>
        <Form.Item
          name="ali1688_offer_list_path"
          label="响应 offerList 点路径"
          extra="从响应 JSON 中取候选列表的点路径，例如 data.offerList"
        >
          <Input placeholder="data.offerList" />
        </Form.Item>
        <Form.Item>
          <Button type="primary" htmlType="submit">保存</Button>
        </Form.Item>
      </Form>
    </Card>
  );
}
