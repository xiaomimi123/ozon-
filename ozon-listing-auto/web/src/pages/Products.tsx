import { useState } from "react";
import { Card, Form, InputNumber, Input, DatePicker, Button, Table, Space, Image, message } from "antd";
import { listProducts, ProductFilter } from "../api/products";

export default function Products() {
  const [taskId, setTaskId] = useState<number>();
  const [data, setData] = useState<{ items: any[]; total: number }>({ items: [], total: 0 });
  const [page, setPage] = useState(1);
  const [form] = Form.useForm();

  const query = async (p = 1) => {
    if (!taskId) { message.warning("请先输入任务ID"); return; }
    const raw: any = form.getFieldsValue();
    const f: ProductFilter = { ...raw };
    if (raw.listed_after && typeof raw.listed_after.toISOString === "function") {
      f.listed_after = raw.listed_after.toISOString();
    }
    try {
      setData(await listProducts(taskId, f, p));
      setPage(p);
    } catch {
      message.error("查询失败，请稍后重试");
    }
  };

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="large">
      <Card title="筛选（条件可空，可改重筛）">
        <Form form={form} layout="inline" onFinish={() => query(1)}>
          <Form.Item label="任务ID"><InputNumber onChange={(v) => setTaskId(v as number)} /></Form.Item>
          <Form.Item name="sales_min" label="月销≥"><InputNumber /></Form.Item>
          <Form.Item name="return_rate_max" label="退货率≤"><InputNumber step={0.01} /></Form.Item>
          <Form.Item name="rating_min" label="评分≥"><InputNumber step={0.1} /></Form.Item>
          <Form.Item name="weight_max" label="重量≤"><InputNumber step={0.1} /></Form.Item>
          <Form.Item name="listed_after" label="上架时间≥"><DatePicker /></Form.Item>
          <Form.Item name="follow_max" label="跟卖数≤"><InputNumber /></Form.Item>
          <Form.Item name="keyword" label="标题"><Input /></Form.Item>
          <Space>
            <Button type="primary" htmlType="submit">应用</Button>
            <Button onClick={() => { form.resetFields(); query(1); }}>重置</Button>
          </Space>
        </Form>
      </Card>
      <Card title={`商品列表（共 ${data.total} 条）`}>
        <Table rowKey="id" dataSource={data.items}
          pagination={{ current: page, total: data.total, pageSize: 20, onChange: (p) => query(p) }}
          columns={[
            { title: "图", dataIndex: "main_image_url", render: (u) => u ? <Image src={u} width={48} /> : "-" },
            { title: "标题", dataIndex: "title" }, { title: "价", dataIndex: "price" },
            { title: "月销", dataIndex: "sales_monthly" }, { title: "评分", dataIndex: "rating" },
            { title: "跟卖数", dataIndex: "follow_count" }, { title: "SKU", dataIndex: "sku" },
          ]} />
      </Card>
    </Space>
  );
}
