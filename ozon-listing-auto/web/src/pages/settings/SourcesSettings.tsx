import { useEffect } from "react";
import { Card, Form, Input, Select, Button, message, Typography } from "antd";
import { getSources, putSources } from "../../api/sources";
import AdvancedSection from "../../components/AdvancedSection";

const DEFAULTS = {
  ali1688_image_search_url: "", ali1688_keyword_search_url: "", ali1688_method: "GET",
  ali1688_extra_params: "", ali1688_extra_headers: "", ali1688_offer_list_path: "data.offerList",
  import_token: "",
  import_1688_list_path: "", import_1688_offer_id_path: "", import_1688_title_path: "",
  import_1688_price_path: "", import_1688_image_path: "", import_1688_shop_path: "",
  import_1688_detail_url_path: "", import_1688_sales_path: "",
};

export default function SourcesSettings() {
  const [form] = Form.useForm();
  useEffect(() => {
    getSources().then((d) => form.setFieldsValue({ ...DEFAULTS, ...d, import_token: "" })).catch(() => {});
  }, []);
  const onFinish = async (values: any) => {
    try { await putSources(values); message.success("货源配置已保存"); }
    catch { message.error("保存失败"); }
  };
  return (
    <Card title="货源配置">
      <Typography.Paragraph type="secondary">
        1688 采集用的接口地址。这些是 1688 内部接口，需要你从浏览器抓包获取；不确定就先留空，1688 采集暂不可用。登录 Cookie 请在「货源账号」页填写，本页不存 Cookie。
      </Typography.Paragraph>
      <Form form={form} layout="vertical" initialValues={DEFAULTS} onFinish={onFinish} style={{ maxWidth: 480 }}>
        <Form.Item name="ali1688_image_search_url" label="1688 图搜接口地址" extra="拍立淘以图搜图的接口地址，从浏览器抓包获取">
          <Input placeholder="https://h5api.m.1688.com/..." />
        </Form.Item>
        <Form.Item name="ali1688_keyword_search_url" label="1688 关键词搜索接口地址" extra="按关键词搜索的接口地址，从浏览器抓包获取">
          <Input placeholder="https://..." />
        </Form.Item>
        <Form.Item name="import_token" label="采集令牌" extra="采集扩展回传用的令牌，需与扩展 options 里填的一致；留空不修改">
          <Input.Password placeholder="留空则不更改" />
        </Form.Item>
        <AdvancedSection>
          <Form.Item name="ali1688_method" label="请求方法" rules={[{ required: true }]} extra="接口是 GET 还是 POST，看抓包">
            <Select options={[{ value: "GET", label: "GET" }, { value: "POST", label: "POST" }]} />
          </Form.Item>
          <Form.Item name="ali1688_extra_params" label="额外请求参数（JSON）" extra="签名等额外参数，JSON 对象字符串，例如 {&quot;sign&quot;: &quot;...&quot;}">
            <Input.TextArea placeholder='{"sign": "..."}' rows={3} />
          </Form.Item>
          <Form.Item name="ali1688_extra_headers" label="额外请求头（JSON）" extra="额外请求头，JSON 对象字符串，例如 {&quot;x-h5-req&quot;: &quot;...&quot;}">
            <Input.TextArea placeholder='{"x-h5-req": "..."}' rows={3} />
          </Form.Item>
          <Form.Item name="ali1688_offer_list_path" label="响应商品列表路径" extra="从返回 JSON 里取商品列表的位置，一般 data.offerList">
            <Input placeholder="data.offerList" />
          </Form.Item>
          <Form.Item name="import_1688_list_path" label="商品列表路径" extra="留空用默认；按『导入商品』页采集原始记录里的真实响应校准">
            <Input placeholder="data.offerList" />
          </Form.Item>
          <Form.Item name="import_1688_offer_id_path" label="商品 ID 路径" extra="留空用默认；按『导入商品』页采集原始记录里的真实响应校准">
            <Input placeholder="offerId" />
          </Form.Item>
          <Form.Item name="import_1688_title_path" label="标题路径" extra="留空用默认；按『导入商品』页采集原始记录里的真实响应校准">
            <Input placeholder="subject" />
          </Form.Item>
          <Form.Item name="import_1688_price_path" label="价格路径" extra="留空用默认；按『导入商品』页采集原始记录里的真实响应校准">
            <Input placeholder="priceInfo.price" />
          </Form.Item>
          <Form.Item name="import_1688_image_path" label="图片路径" extra="留空用默认；按『导入商品』页采集原始记录里的真实响应校准">
            <Input placeholder="imageUrl" />
          </Form.Item>
          <Form.Item name="import_1688_shop_path" label="店铺名路径" extra="留空用默认；按『导入商品』页采集原始记录里的真实响应校准">
            <Input placeholder="company.name" />
          </Form.Item>
          <Form.Item name="import_1688_detail_url_path" label="详情链接路径" extra="留空用默认；按『导入商品』页采集原始记录里的真实响应校准">
            <Input placeholder="detailUrl" />
          </Form.Item>
          <Form.Item name="import_1688_sales_path" label="销量路径" extra="留空用默认；按『导入商品』页采集原始记录里的真实响应校准">
            <Input placeholder="monthSold" />
          </Form.Item>
        </AdvancedSection>
        <Form.Item>
          <Button type="primary" htmlType="submit">保存</Button>
        </Form.Item>
      </Form>
    </Card>
  );
}
