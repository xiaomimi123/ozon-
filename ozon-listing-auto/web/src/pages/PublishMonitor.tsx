import { useEffect, useRef, useState } from "react";
import { Card, Form, InputNumber, Switch, Button, Space, Row, Col, Statistic, message } from "antd";
import { getPace, savePace, Pace } from "../api/pace";
import { schedule, tick, getMonitor } from "../api/publish";

const STATUSES = ["draft", "confirmed", "scheduled", "pending_review", "published", "failed"];
const LABEL: Record<string, string> = { draft: "草稿", confirmed: "已确认", scheduled: "已排期", pending_review: "审核中", published: "已上架", failed: "失败" };

export default function PublishMonitor() {
  const [taskId, setTaskId] = useState<number>();
  const [mon, setMon] = useState<any>({ counts: {}, next_scheduled_at: null });
  const [form] = Form.useForm();
  const wsRef = useRef<WebSocket | null>(null);

  const loadMon = async () => { if (!taskId) return; setMon(await getMonitor(taskId)); };
  const loadPace = async () => { if (!taskId) return; const p = await getPace(taskId);
    form.setFieldsValue({ ...p, ah0: p.active_hours?.[0] ?? 9, ah1: p.active_hours?.[1] ?? 23 }); };

  useEffect(() => { if (!taskId) return; loadPace(); loadMon();
    // 实时 WS(断开回退轮询)
    let poll: any;
    const startPoll = () => { if (!poll) poll = setInterval(loadMon, 5000); };
    try {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}/ws/progress`);
      ws.onmessage = () => loadMon();
      ws.onerror = () => startPoll();
      ws.onclose = () => startPoll();
      wsRef.current = ws;
    } catch { startPoll(); }
    return () => { wsRef.current?.close(); if (poll) clearInterval(poll); };
  }, [taskId]);

  const onSavePace = async (v: any) => {
    const body: Pace = { min_interval_sec: v.min_interval_sec, max_interval_sec: v.max_interval_sec,
      daily_limit: v.daily_limit, active_hours: [v.ah0, v.ah1], wait_ozon_approval: v.wait_ozon_approval };
    await savePace(taskId!, body); message.success("节奏已保存"); };
  const onSchedule = async () => { if (!taskId) return; const r = await schedule(taskId); message.success(`排期 ${r.scheduled} 条`); loadMon(); };
  const onTick = async () => { if (!taskId) return; const r = await tick(taskId); message.success(`本次上架 ${r.published}, 审核中 ${r.pending_review}, 失败 ${r.failed}`); loadMon(); };

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="large">
      <Card title="上架监控 PublishMonitor">
        <Space>任务ID <InputNumber onChange={(v) => setTaskId(v as number)} />
          <Button type="primary" onClick={onSchedule}>开始排期</Button>
          <Button onClick={onTick}>手动上架一条</Button>
          <Button onClick={loadMon}>刷新</Button></Space>
      </Card>
      <Card title="节奏配置">
        <Form form={form} layout="inline" onFinish={onSavePace}
          initialValues={{ min_interval_sec: 60, max_interval_sec: 180, daily_limit: 200, ah0: 9, ah1: 23, wait_ozon_approval: true }}>
          <Form.Item name="min_interval_sec" label="最小间隔(秒)"><InputNumber min={0} /></Form.Item>
          <Form.Item name="max_interval_sec" label="最大间隔(秒)"><InputNumber min={0} /></Form.Item>
          <Form.Item name="daily_limit" label="每日上限"><InputNumber min={1} /></Form.Item>
          <Form.Item name="ah0" label="时段起"><InputNumber min={0} max={24} /></Form.Item>
          <Form.Item name="ah1" label="时段止"><InputNumber min={0} max={24} /></Form.Item>
          <Form.Item name="wait_ozon_approval" label="等审核" valuePropName="checked"><Switch /></Form.Item>
          <Button type="primary" htmlType="submit">保存节奏</Button>
        </Form>
      </Card>
      <Card title={`队列监控 · 下一条: ${mon.next_scheduled_at ?? "-"}`}>
        <Row gutter={16}>
          {STATUSES.map((st) => (
            <Col key={st} span={4}><Statistic title={LABEL[st]} value={mon.counts?.[st] ?? 0} /></Col>
          ))}
        </Row>
      </Card>
    </Space>
  );
}
