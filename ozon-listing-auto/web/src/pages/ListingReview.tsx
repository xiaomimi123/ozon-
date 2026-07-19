import { useState } from "react";
import { Card, InputNumber, Select, Button, Table, Space, Tag, Modal, Form, Input, Image, message } from "antd";
import { buildDrafts, getDrafts, confirmDraft, autoConfirm, publishDrafts } from "../api/listing";
import { listShops } from "../api/shops";
import { getCategories, suggestCategory, confirmCategory } from "../api/category";
import { useEffect } from "react";

const ST: Record<string, string> = { draft: "default", confirmed: "blue", published: "green", failed: "red", below_min: "orange" };

export default function ListingReview() {
  const [taskId, setTaskId] = useState<number>();
  const [shopId, setShopId] = useState<number>();
  const [shops, setShops] = useState<any[]>([]);
  const [rows, setRows] = useState<any[]>([]);
  const [categories, setCategories] = useState<any[]>([]);
  const [catModalOpen, setCatModalOpen] = useState(false);
  const [editingRow, setEditingRow] = useState<any>(null);
  const [catForm] = Form.useForm();
  useEffect(() => { listShops().then(setShops).catch(() => {}); }, []);
  useEffect(() => { getCategories().then(setCategories).catch(() => {}); }, []);
  const load = async () => { if (!taskId) { message.warning("请先输入任务ID"); return; } setRows(await getDrafts(taskId)); };
  const onBuild = async () => { if (!taskId) return; const r = await buildDrafts(taskId, shopId); message.success(`生成 ${r.built} 条(拦截 ${r.blocked})`); load(); };
  const onConfirm = async (id: number) => {
    const res = await confirmDraft(id);
    if (res?.error) { message.warning(res.error); } else { message.success("已确认"); }
    load();
  };
  const onAuto = async () => { if (!taskId) return; const r = await autoConfirm(taskId); message.success(`自动确认 ${r.confirmed} 条`); load(); };
  const onPublish = async () => { if (!taskId) return; const r = await publishDrafts(taskId); message.success(`挂靠 ${r.published} 条(失败 ${r.failed})`); load(); };

  const openCatModal = (row: any) => {
    setEditingRow(row);
    catForm.setFieldsValue({
      category_id: row.category_id,
      attributesJson: JSON.stringify(row.attributes ?? {}, null, 2),
    });
    setCatModalOpen(true);
  };
  const onSuggestCategory = async () => {
    if (!editingRow) return;
    const r = await suggestCategory(editingRow.candidate_id);
    catForm.setFieldsValue({ category_id: r.category_id, attributesJson: JSON.stringify(r.attributes ?? {}, null, 2) });
    message.success(`LLM 建议来源: ${r.source}`);
  };
  const onConfirmCategory = async () => {
    if (!editingRow) return;
    const values = await catForm.validateFields();
    let attributes: any = {};
    try { attributes = values.attributesJson ? JSON.parse(values.attributesJson) : {}; }
    catch { message.error("属性 JSON 格式错误"); return; }
    const path = categories.find((c) => c.id === values.category_id)?.path;
    await confirmCategory(editingRow.id, { category_id: values.category_id, attributes, path });
    message.success("类目属性已确认");
    setCatModalOpen(false);
    load();
  };

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
        <Table rowKey="id" dataSource={rows} pagination={false} scroll={{ x: "max-content" }}
          columns={[
            { title: "模式", dataIndex: "mode", render: (m) => <Tag>{m === "create" ? "自建" : "跟卖"}</Tag> },
            { title: "标题", dataIndex: "title", render: (t) => t ?? "-" },
            { title: "目标卡 SKU", dataIndex: "target_ozon_sku" },
            { title: "进价(到手)", dataIndex: "cost" },
            { title: "售价 RUB", dataIndex: "price" },
            { title: "毛利率", dataIndex: "margin", render: (m) => (m != null ? `${(m * 100).toFixed(1)}%` : "-") },
            { title: "库存", dataIndex: "stock_qty" },
            { title: "状态", dataIndex: "status", render: (s) => <Tag color={ST[s]}>{s}</Tag> },
            { title: "Ozon结果", dataIndex: "ozon_result", render: (r) => r?.ozon_product_id ?? "-" },
            { title: "操作", render: (_, r) => (
                <Space>
                  {r.mode === "create" && <Button size="small" onClick={() => openCatModal(r)}>类目/属性/图片</Button>}
                  {r.status === "draft" && <Button size="small" onClick={() => onConfirm(r.id)}>确认草稿</Button>}
                </Space>
              ) },
          ]} />
      </Card>
      <Modal title="确认类目/属性/图片" open={catModalOpen} onCancel={() => setCatModalOpen(false)}
        onOk={onConfirmCategory} okText="确认类目属性" cancelText="取消" destroyOnClose>
        {editingRow && (
          <Space direction="vertical" style={{ width: "100%" }}>
            <div><b>标题：</b>{editingRow.title ?? "-"}</div>
            <div><b>描述：</b>{editingRow.description ?? "-"}</div>
            <div>
              <b>已确认图片：</b>
              <Space wrap>
                {(editingRow.images ?? []).length > 0
                  ? (editingRow.images as string[]).map((u, i) => <Image key={i} src={u} width={64} height={64} style={{ objectFit: "cover" }} />)
                  : <span>暂无</span>}
              </Space>
            </div>
            <Form form={catForm} layout="vertical">
              <Form.Item label={<Space>类目 <Button size="small" onClick={onSuggestCategory}>LLM 建议</Button></Space>}
                name="category_id" rules={[{ required: true, message: "请选择类目" }]}>
                <Select placeholder="选择类目"
                  options={categories.map((c) => ({ value: c.id, label: `${c.name}（${c.path}）` }))} />
              </Form.Item>
              <Form.Item label="属性(JSON)" name="attributesJson">
                <Input.TextArea rows={6} placeholder="{}" />
              </Form.Item>
            </Form>
          </Space>
        )}
      </Modal>
    </Space>
  );
}
