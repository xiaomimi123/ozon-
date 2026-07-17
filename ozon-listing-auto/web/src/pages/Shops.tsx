import { useEffect, useState } from "react";
import { Card, Form, Input, Switch, Button, Table, Space, message, Popconfirm } from "antd";
import { listShops, createShop, deleteShop } from "../api/shops";

export default function Shops() {
  const [rows, setRows] = useState<any[]>([]);
  const [form] = Form.useForm();
  const load = () => listShops().then(setRows);
  useEffect(() => { load(); }, []);
  const onCreate = async (v: any) => {
    await createShop({ name: v.name, client_id: v.client_id, api_key: v.api_key, is_sandbox: v.is_sandbox ?? true });
    message.success("已添加店铺"); form.resetFields(); load(); };
  const onDelete = async (id: number) => { await deleteShop(id); message.success("已删除"); load(); };
  return (
    <Space direction="vertical" style={{ width: "100%" }} size="large">
      <Card title="新增 Ozon 店铺">
        <Form form={form} layout="inline" onFinish={onCreate} initialValues={{ is_sandbox: true }}>
          <Form.Item name="name" rules={[{ required: true }]}><Input placeholder="店铺名" /></Form.Item>
          <Form.Item name="client_id" rules={[{ required: true }]}><Input placeholder="Client-Id" /></Form.Item>
          <Form.Item name="api_key" rules={[{ required: true }]}><Input.Password placeholder="Api-Key" /></Form.Item>
          <Form.Item name="is_sandbox" label="沙箱" valuePropName="checked"><Switch /></Form.Item>
          <Button type="primary" htmlType="submit">添加</Button>
        </Form>
      </Card>
      <Card title="店铺列表">
        <Table rowKey="id" dataSource={rows} pagination={false}
          columns={[
            { title: "名称", dataIndex: "name" }, { title: "Client-Id", dataIndex: "client_id" },
            { title: "沙箱", dataIndex: "is_sandbox", render: (b) => (b ? "是" : "否") },
            { title: "启用", dataIndex: "is_active", render: (b) => (b ? "是" : "否") },
            { title: "操作", render: (_, r) => <Popconfirm title="删除?" onConfirm={() => onDelete(r.id)}><Button danger size="small">删除</Button></Popconfirm> },
          ]} />
      </Card>
    </Space>
  );
}
