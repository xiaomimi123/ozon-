import { useState } from "react";
import { Card, InputNumber, Button, Row, Col, Tag, Space, message, Image, Descriptions, Popconfirm } from "antd";
import { startScore, getQueue, decide, autoAdopt } from "../api/review";

const TIER_COLOR: Record<string, string> = { auto: "green", review: "gold", rejected: "red" };

export default function ReviewBoard() {
  const [taskId, setTaskId] = useState<number>();
  const [items, setItems] = useState<any[]>([]);
  const [idx, setIdx] = useState(0);

  const load = async () => { if (!taskId) { message.warning("请先输入任务ID"); return; }
    const q = await getQueue(taskId); setItems(q.items); setIdx(0); };
  const onScore = async () => { if (!taskId) return; await startScore(taskId); message.success("评分完成"); load(); };
  const onDecide = async (cid: number, d: "adopt" | "reject") => {
    await decide(cid, d); message.success(d === "adopt" ? "已采用" : "已拒绝"); load(); };
  const onAutoAdopt = async () => { if (!taskId) return; const r = await autoAdopt(taskId);
    message.success(`自动采用 ${r.auto_adopted} 条`); load(); };

  const cur = items[idx];
  return (
    <Space direction="vertical" style={{ width: "100%" }} size="large">
      <Card title="审核台">
        <Space>
          任务ID <InputNumber onChange={(v) => setTaskId(v as number)} />
          <Button type="primary" onClick={onScore}>开始评分</Button>
          <Button onClick={load}>拉取审核队列</Button>
          <Popconfirm title="关闭人工审核将按阈值自动采用达标候选，确认？" onConfirm={onAutoAdopt}>
            <Button danger>关闭审核·自动采用</Button>
          </Popconfirm>
        </Space>
      </Card>
      {cur && (
        <Row gutter={16}>
          <Col span={8}>
            <Card title={`Ozon 商品 (${idx + 1}/${items.length})`}>
              {cur.product.main_image_url && <Image src={cur.product.main_image_url} width={120} />}
              <Descriptions column={1} size="small">
                <Descriptions.Item label="标题">{cur.product.title}</Descriptions.Item>
                <Descriptions.Item label="SKU">{cur.product.sku}</Descriptions.Item>
                <Descriptions.Item label="价">{cur.product.price}</Descriptions.Item>
              </Descriptions>
              <Space>
                <Button disabled={idx === 0} onClick={() => setIdx(idx - 1)}>上一条</Button>
                <Button disabled={idx >= items.length - 1} onClick={() => setIdx(idx + 1)}>下一条</Button>
              </Space>
            </Card>
          </Col>
          <Col span={16}>
            <Space direction="vertical" style={{ width: "100%" }}>
              {cur.candidates.map((c: any) => (
                <Card key={c.id} size="small"
                  title={<Space><Tag color={c.platform === "ali1688" ? "blue" : "magenta"}>{c.platform}</Tag>
                    {c.title}<Tag color={TIER_COLOR[c.tier]}>{c.tier} · {c.score_total?.toFixed(1)}</Tag></Space>}
                  extra={<Space>
                    <Button type="primary" size="small" onClick={() => onDecide(c.id, "adopt")}>采用</Button>
                    <Button danger size="small" onClick={() => onDecide(c.id, "reject")}>拒绝</Button></Space>}>
                  <Space size="large">
                    <span>图 {c.scores.image?.toFixed(0)}</span><span>标题 {c.scores.title?.toFixed(0)}</span>
                    <span>属性 {c.scores.attr?.toFixed(0)}</span><span>价 {c.scores.price?.toFixed(0)}</span>
                    <span>供应商 {c.scores.supplier?.toFixed(0)}</span><span>价格 ¥{c.price}</span>
                  </Space>
                </Card>
              ))}
            </Space>
          </Col>
        </Row>
      )}
    </Space>
  );
}
