import { useState } from "react";
import { Card, InputNumber, Select, Button, Space, Row, Col, Image, Tag, Empty, message } from "antd";
import { processImages, listImages, approveImage, rejectImage } from "../api/images";

const ST: Record<string, string> = { pending: "default", processing: "processing", done: "blue", failed: "red", approved: "green", rejected: "red" };
const OP_LABEL: Record<string, string> = { rmbg: "去背景", whitebg: "白底", watermark: "去水印", crop_norm: "裁剪归一", gen: "AI 生图" };

export default function ImageStudio() {
  const [taskId, setTaskId] = useState<number>();
  const [status, setStatus] = useState<string>();
  const [rows, setRows] = useState<any[]>([]);

  const load = async () => {
    if (!taskId) { message.warning("请先输入任务ID"); return; }
    setRows(await listImages(taskId, status));
  };
  const onProcess = async () => {
    if (!taskId) { message.warning("请先输入任务ID"); return; }
    const r = await processImages(taskId);
    message.success(`处理完成 ${r.processed} 张(失败 ${r.failed})`);
    load();
  };
  const onApprove = async (id: number) => { await approveImage(id); message.success("已采用"); load(); };
  const onReject = async (id: number) => { await rejectImage(id); message.success("已弃用"); load(); };

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="large">
      <Card title="图片工作室 ImageStudio">
        <Space wrap>
          任务ID <InputNumber onChange={(v) => setTaskId(v as number)} />
          状态 <Select style={{ width: 140 }} allowClear placeholder="全部" onChange={(v) => setStatus(v)}
            options={[
              { value: "pending", label: "待处理" }, { value: "done", label: "已完成" },
              { value: "failed", label: "失败" }, { value: "approved", label: "已采用" }, { value: "rejected", label: "已弃用" },
            ]} />
          <Button type="primary" onClick={onProcess}>开始改图</Button>
          <Button onClick={load}>刷新</Button>
        </Space>
      </Card>
      <Card title="产物网格">
        {rows.length === 0 ? <Empty description="暂无图片" /> : (
          <Row gutter={[16, 16]}>
            {rows.map((img) => (
              <Col key={img.id} span={6}>
                <Card size="small" title={OP_LABEL[img.op] ?? img.op}
                  cover={<Image src={img.result_url || img.source_url} height={160} style={{ objectFit: "cover" }}
                    fallback="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBTAA7" />}>
                  <Space direction="vertical" size={4} style={{ width: "100%" }}>
                    <Tag color={ST[img.status]}>{img.status}</Tag>
                    <span>候选 #{img.candidate_id} · {img.provider}</span>
                    <Space>
                      <Button size="small" type="primary" onClick={() => onApprove(img.id)}>采用</Button>
                      <Button size="small" danger onClick={() => onReject(img.id)}>弃用</Button>
                    </Space>
                  </Space>
                </Card>
              </Col>
            ))}
          </Row>
        )}
      </Card>
    </Space>
  );
}
