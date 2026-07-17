import { useEffect, useState } from "react";
import { Card, Form, Input, Select, Switch, InputNumber, Button, Table, Space, message, Tag } from "antd";
import { createTask, listTasks, startCollect, pauseCollect, TaskBody } from "../api/tasks";

export default function Tasks() {
  const [rows, setRows] = useState<any[]>([]);
  const [form] = Form.useForm();
  const refresh = () => listTasks().then(setRows);
  useEffect(() => { refresh(); }, []);

  const onCreate = async (v: any) => {
    const body: TaskBody = {
      name: v.name, listing_mode: v.listing_mode, entry_type: v.entry_type, entry_value: v.entry_value,
      provider: v.provider, source_platforms: v.source_platforms || [],
      review_config: { source_review_required: v.source_review_required ?? true, source_score_min: v.source_score_min ?? null },
    };
    await createTask(body); message.success("任务已创建"); form.resetFields(); refresh();
  };
  const onStart = async (id: number) => { await startCollect(id); message.success("采集完成"); refresh(); };
  const onPause = async (id: number) => { await pauseCollect(id); message.info("已暂停"); refresh(); };

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="large">
      <Card title="新建采集任务">
        <Form form={form} layout="inline" onFinish={onCreate}
          initialValues={{ listing_mode: "follow", entry_type: "keyword", provider: "mock", source_platforms: ["ali1688"], source_review_required: true }}>
          <Form.Item name="name" rules={[{ required: true }]}><Input placeholder="任务名" /></Form.Item>
          <Form.Item name="listing_mode" label="模式">
            <Select style={{ width: 110 }} options={[{ value: "follow", label: "跟卖" }, { value: "create", label: "自建" }]} />
          </Form.Item>
          <Form.Item name="entry_type" label="入口">
            <Select style={{ width: 120 }} options={[
              { value: "keyword", label: "关键词" }, { value: "category", label: "类目" },
              { value: "seller", label: "竞品店铺" }, { value: "own_shop", label: "自有店" }]} />
          </Form.Item>
          <Form.Item name="entry_value" rules={[{ required: true }]}><Input placeholder="关键词/类目URL/卖家ID" /></Form.Item>
          <Form.Item name="provider" label="采集源">
            <Select style={{ width: 120 }} options={[{ value: "mock", label: "Mock" }, { value: "composer", label: "爬虫" }, { value: "apify", label: "Apify" }]} />
          </Form.Item>
          <Form.Item name="source_platforms" label="货源">
            <Select mode="multiple" style={{ width: 180 }} options={[{ value: "ali1688", label: "1688" }, { value: "pinduoduo", label: "拼多多" }]} />
          </Form.Item>
          <Form.Item name="source_review_required" label="需审核" valuePropName="checked"><Switch /></Form.Item>
          <Form.Item name="source_score_min" label="阈值"><InputNumber placeholder="可空" /></Form.Item>
          <Button type="primary" htmlType="submit">创建</Button>
        </Form>
      </Card>
      <Card title="任务列表">
        <Table rowKey="id" dataSource={rows} pagination={false}
          columns={[
            { title: "ID", dataIndex: "id" }, { title: "名称", dataIndex: "name" },
            { title: "模式", dataIndex: "listing_mode", render: (v) => <Tag color={v === "follow" ? "blue" : "green"}>{v === "follow" ? "跟卖" : "自建"}</Tag> },
            { title: "入口", dataIndex: "entry_type" }, { title: "采集源", dataIndex: "provider" },
            { title: "状态", dataIndex: "status" },
            { title: "统计", dataIndex: "stats", render: (s) => s ? `入库${s.inserted ?? 0}/去重${s.skipped ?? 0}` : "-" },
            { title: "操作", render: (_, r) => <Space>
                <Button size="small" onClick={() => onStart(r.id)}>启动</Button>
                <Button size="small" onClick={() => onPause(r.id)}>暂停</Button></Space> },
          ]} />
      </Card>
    </Space>
  );
}
