import { useState } from "react";
import { Card, InputNumber, Select, Button, Table, Space, Tag, message } from "antd";
import { buildDrafts, getDrafts, confirmDraft, autoConfirm, publishDrafts } from "../api/listing";
import { listShops } from "../api/shops";
import { useEffect } from "react";

const ST: Record<string, string> = { draft: "default", confirmed: "blue", published: "green", failed: "red", below_min: "orange" };

export default function ListingReview() {
  const [taskId, setTaskId] = useState<number>();
  const [shopId, setShopId] = useState<number>();
  const [shops, setShops] = useState<any[]>([]);
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => { listShops().then(setShops).catch(() => {}); }, []);
  const load = async () => { if (!taskId) { message.warning("请先输入任务ID"); return; } setRows(await getDrafts(taskId)); };
  const onBuild = async () => { if (!taskId) return; const r = await buildDrafts(taskId, shopId); message.success(`生成 ${r.built} 条(拦截 ${r.blocked})`); load(); };
  const onConfirm = async (id: number) => { await confirmDraft(id); message.success("已确认"); load(); };
  const onAuto = async () => { if (!taskId) return; const r = await autoConfirm(taskId); message.success(`自动确认 ${r.confirmed} 条`); load(); };
  const onPublish = async () => { if (!taskId) return; const r = await publishDrafts(taskId); message.success(`挂靠 ${r.published} 条(失败 ${r.failed})`); load(); };

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="large">
      <Card title="上架审核(跟卖草稿)">
        <Space wrap>
          任务ID <InputNumber onChange={(v) => setTaskId(v as number)} />
          店铺 <Select style={{ width: 180 }} allowClear onChange={(v) => setShopId(v)}
            options={shops.map((s) => ({ value: s.id, label: `${s.name}${s.is_sandbox ? "(沙箱)" : ""}` }))} />
          <Button type="primary" onClick={onBuild}>生成草稿</Button>
          <Button onClick={load}>刷新</Button>
          <Button onClick={onAuto}>按开关自动确认</Button>
          <Button danger onClick={onPublish}>挂靠上架</Button>
        </Space>
      </Card>
      <Card title="草稿列表">
        <Table rowKey="id" dataSource={rows} pagination={false}
          columns={[
            { title: "目标卡 SKU", dataIndex: "target_ozon_sku" },
            { title: "进价(到手)", dataIndex: "cost" },
            { title: "售价 RUB", dataIndex: "price" },
            { title: "毛利率", dataIndex: "margin", render: (m) => (m != null ? `${(m * 100).toFixed(1)}%` : "-") },
            { title: "库存", dataIndex: "stock_qty" },
            { title: "状态", dataIndex: "status", render: (s) => <Tag color={ST[s]}>{s}</Tag> },
            { title: "Ozon结果", dataIndex: "ozon_result", render: (r) => r?.ozon_product_id ?? "-" },
            { title: "操作", render: (_, r) => r.status === "draft"
                ? <Button size="small" onClick={() => onConfirm(r.id)}>确认</Button> : null },
          ]} />
      </Card>
    </Space>
  );
}
