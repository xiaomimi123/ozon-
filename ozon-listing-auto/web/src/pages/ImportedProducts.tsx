import { useEffect, useState } from "react";
import { Card, Table, Image, Typography, Button, message, Upload, Space } from "antd";
import { listImported, uploadExcel } from "../api/importer";

const fmt = (v?: string) => (v ? String(v).replace("T", " ").slice(0, 19) : "-");

export default function ImportedProducts() {
  const [rows, setRows] = useState<any[]>([]);
  const load = () => listImported().then(setRows).catch(() => message.error("加载失败"));
  useEffect(() => { load(); }, []);
  const onUpload = async (file: File) => {
    try { const r = await uploadExcel(file); message.success(`导入 ${r.parsed} 条(去重跳过 ${r.captured - r.parsed})`); load(); }
    catch (e: any) { message.error(e?.response?.data?.detail || "导入失败"); }
    return false; // 阻止 antd 默认上传
  };
  return (
    <Card title="导入商品" extra={
      <Space>
        <Upload accept=".xlsx" showUploadList={false} beforeUpload={onUpload}>
          <Button type="primary">上传 Excel（1688 采购助手导出）</Button>
        </Upload>
        <Button onClick={load}>刷新</Button>
      </Space>
    }>
      <Typography.Paragraph type="secondary">
        数据来自采集扩展回传。若有采集记录但此处为空，说明解析字段路径与真实响应不符——去「货源配置」按采集原始记录调整 import_1688_*_path。
      </Typography.Paragraph>
      <Table rowKey="id" dataSource={rows} pagination={{ pageSize: 20 }} scroll={{ x: "max-content" }}
        columns={[
          { title: "图", dataIndex: "image_url", width: 80, render: (u) => (u ? <Image src={u} width={48} /> : "-") },
          { title: "标题", dataIndex: "title", width: 280 },
          { title: "价", dataIndex: "price", width: 90, render: (v) => (v == null ? "-" : `¥${v}`) },
          { title: "店铺", dataIndex: "shop_name", width: 140 },
          { title: "销量", dataIndex: "sales", width: 90 },
          { title: "offerId", dataIndex: "offer_id", width: 120 },
          { title: "详情", dataIndex: "detail_url", width: 80, render: (u) => (u ? <a href={u} target="_blank" rel="noreferrer">打开</a> : "-") },
          { title: "采集时间", dataIndex: "created_at", width: 170, render: fmt },
        ]} />
    </Card>
  );
}
