import { useEffect, useState } from "react";
import { Card, Form, Input, InputNumber, Select, Button, Table, Space, Tag, Modal, Popconfirm, message } from "antd";
import { listAccounts, createAccount, updateAccount, deleteAccount } from "../../api/sourceAccounts";

const PLATFORM_LABEL: Record<string, string> = { ali1688: "1688", pinduoduo: "拼多多" };
const PLATFORM_OPTIONS = Object.entries(PLATFORM_LABEL).map(([value, label]) => ({ value, label }));
const STATUS_LABEL: Record<string, string> = { active: "可用", cooldown: "冷却中", disabled: "停用" };
const STATUS_COLOR: Record<string, string> = { active: "success", cooldown: "orange", disabled: "default" };

function errMsg(err: any, fallback: string) {
  return err?.response?.data?.detail || fallback;
}
const fmt = (v?: string) => (v ? String(v).replace("T", " ").slice(0, 19) : "-");

export default function SourceAccounts() {
  const [rows, setRows] = useState<any[]>([]);
  const [form] = Form.useForm();
  const [ckAccount, setCkAccount] = useState<any>(null);
  const [ckForm] = Form.useForm();

  const load = () => listAccounts().then(setRows);
  useEffect(() => { load(); }, []);

  const onCreate = async (v: any) => {
    try {
      await createAccount({ platform: v.platform, label: v.label, credentials: { cookie: v.cookie },
        daily_limit: v.daily_limit, min_interval_sec: v.min_interval_sec });
      message.success("已添加账号"); form.resetFields(); load();
    } catch (err) { message.error(errMsg(err, "添加失败")); }
  };
  const onToggle = async (r: any) => {
    try { await updateAccount(r.id, { status: r.status === "disabled" ? "active" : "disabled" });
      message.success("已更新"); load(); } catch (err) { message.error(errMsg(err, "操作失败")); }
  };
  const onRestore = async (r: any) => {
    try { await updateAccount(r.id, { status: "active" }); message.success("已恢复为可用"); load(); }
    catch (err) { message.error(errMsg(err, "操作失败")); }
  };
  const onDelete = async (id: number) => {
    try { await deleteAccount(id); message.success("已删除"); load(); }
    catch (err) { message.error(errMsg(err, "操作失败")); }
  };
  const onUpdateCookie = async (v: any) => {
    try { await updateAccount(ckAccount.id, { credentials: { cookie: v.cookie } });
      message.success("Cookie 已更新"); setCkAccount(null); ckForm.resetFields(); }
    catch (err) { message.error(errMsg(err, "更新失败")); }
  };

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="large">
      <Card title="添加账号">
        <Form form={form} layout="vertical" onFinish={onCreate}
          initialValues={{ platform: "pinduoduo", daily_limit: 200, min_interval_sec: 6 }} style={{ maxWidth: 560 }}>
          <Form.Item name="platform" label="平台" rules={[{ required: true }]}>
            <Select options={PLATFORM_OPTIONS} style={{ width: 160 }} />
          </Form.Item>
          <Form.Item name="label" label="标签"><Input placeholder="便于识别，如 号1" /></Form.Item>
          <Form.Item name="cookie" label="Cookie" rules={[{ required: true, message: "请粘贴登录 Cookie" }]}>
            <Input.TextArea rows={3} placeholder="登录后从浏览器复制整条 Cookie" />
          </Form.Item>
          <Space>
            <Form.Item name="daily_limit" label="日上限"><InputNumber min={1} /></Form.Item>
            <Form.Item name="min_interval_sec" label="最小间隔(秒)"><InputNumber min={0} /></Form.Item>
          </Space>
          <Form.Item><Button type="primary" htmlType="submit">新增账号</Button></Form.Item>
        </Form>
      </Card>
      <Card title="货源账号列表">
        <Table rowKey="id" dataSource={rows} pagination={false} scroll={{ x: "max-content" }}
          columns={[
            { title: "平台", dataIndex: "platform", width: 90, render: (p) => <Tag>{PLATFORM_LABEL[p] || p}</Tag> },
            { title: "标签", dataIndex: "label", width: 120 },
            { title: "状态", dataIndex: "status", width: 90,
              render: (s) => <Tag color={STATUS_COLOR[s]}>{STATUS_LABEL[s] || s}</Tag> },
            { title: "用量", width: 90, render: (_, r) => `${r.daily_used_count}/${r.daily_limit}` },
            { title: "最小间隔", dataIndex: "min_interval_sec", width: 90 },
            { title: "风控次数", dataIndex: "risk_hits", width: 90 },
            { title: "冷却至", dataIndex: "cooldown_until", width: 170, render: fmt },
            { title: "创建时间", dataIndex: "created_at", width: 170, render: fmt },
            { title: "操作", width: 300, render: (_, r) => (
              <Space>
                <Button size="small" onClick={() => onToggle(r)}>{r.status === "disabled" ? "启用" : "停用"}</Button>
                {r.status === "cooldown" && <Button size="small" onClick={() => onRestore(r)}>手动恢复</Button>}
                <Button size="small" onClick={() => setCkAccount(r)}>更新 Cookie</Button>
                <Popconfirm title="删除该账号?" onConfirm={() => onDelete(r.id)}>
                  <Button size="small" danger>删除</Button>
                </Popconfirm>
              </Space>
            ) },
          ]} />
      </Card>
      <Modal title={`更新 Cookie - ${ckAccount?.label ?? ckAccount?.id ?? ""}`} open={!!ckAccount}
        onCancel={() => { setCkAccount(null); ckForm.resetFields(); }} onOk={() => ckForm.submit()} destroyOnClose>
        <Form form={ckForm} layout="vertical" onFinish={onUpdateCookie}>
          <Form.Item name="cookie" label="新 Cookie" rules={[{ required: true, message: "请粘贴新 Cookie" }]}>
            <Input.TextArea rows={3} placeholder="粘贴新的登录 Cookie（不显示旧值）" />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
