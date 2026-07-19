import { useEffect, useState } from "react";
import { Card, Form, Input, Select, Button, Table, Space, Tag, Modal, Popconfirm, message } from "antd";
import { listUsers, createUser, updateUser, resetPassword, deleteUser } from "../../api/users";

const ROLE_LABEL: Record<string, string> = {
  admin: "管理员",
  operator: "操作员",
  reviewer: "审核员",
  publisher: "发布员",
};
const ROLE_COLOR: Record<string, string> = {
  admin: "red",
  operator: "blue",
  reviewer: "gold",
  publisher: "green",
};
const ROLE_OPTIONS = Object.entries(ROLE_LABEL).map(([value, label]) => ({ value, label }));

function errMsg(err: any, fallback: string) {
  return err?.response?.data?.detail || fallback;
}

export default function StaffSettings() {
  const [rows, setRows] = useState<any[]>([]);
  const [form] = Form.useForm();
  const [pwdUser, setPwdUser] = useState<any>(null);
  const [pwdForm] = Form.useForm();

  const load = () => listUsers().then(setRows);
  useEffect(() => {
    load();
  }, []);

  const onCreate = async (v: any) => {
    try {
      await createUser({ username: v.username, password: v.password, role: v.role });
      message.success("已添加员工");
      form.resetFields();
      load();
    } catch (err) {
      message.error(errMsg(err, "添加失败"));
    }
  };

  const onChangeRole = async (id: number, role: string) => {
    try {
      await updateUser(id, { role });
      message.success("角色已更新");
      load();
    } catch (err) {
      message.error(errMsg(err, "操作失败"));
    }
  };

  const onToggleActive = async (r: any) => {
    try {
      await updateUser(r.id, { is_active: !r.is_active });
      message.success(r.is_active ? "已停用" : "已启用");
      load();
    } catch (err) {
      message.error(errMsg(err, "操作失败"));
    }
  };

  const onDelete = async (id: number) => {
    try {
      await deleteUser(id);
      message.success("已删除");
      load();
    } catch (err) {
      message.error(errMsg(err, "操作失败"));
    }
  };

  const onResetPassword = async (v: any) => {
    try {
      await resetPassword(pwdUser.id, v.password);
      message.success("密码已重置");
      setPwdUser(null);
      pwdForm.resetFields();
    } catch (err) {
      message.error(errMsg(err, "重置失败"));
    }
  };

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="large">
      <Card title="新增员工">
        <Form form={form} layout="inline" onFinish={onCreate} initialValues={{ role: "operator" }}>
          <Form.Item name="username" rules={[{ required: true, message: "请输入用户名" }]}>
            <Input placeholder="用户名" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: "请输入密码" }]}>
            <Input.Password placeholder="密码" />
          </Form.Item>
          <Form.Item name="role" rules={[{ required: true }]}>
            <Select style={{ width: 120 }} options={ROLE_OPTIONS} />
          </Form.Item>
          <Button type="primary" htmlType="submit">
            新增员工
          </Button>
        </Form>
      </Card>
      <Card title="员工列表">
        <Table
          rowKey="id"
          dataSource={rows}
          pagination={false}
          scroll={{ x: "max-content" }}
          columns={[
            { title: "用户名", dataIndex: "username", width: 100 },
            {
              title: "角色",
              dataIndex: "role",
              width: 80,
              render: (role) => <Tag color={ROLE_COLOR[role]}>{ROLE_LABEL[role] || role}</Tag>,
            },
            {
              title: "状态",
              dataIndex: "is_active",
              width: 80,
              render: (active) => <Tag color={active ? "success" : "default"}>{active ? "启用" : "停用"}</Tag>,
            },
            {
              title: "创建时间",
              dataIndex: "created_at",
              width: 170,
              render: (v) => (v ? String(v).replace("T", " ").slice(0, 19) : "-"),
            },
            {
              title: "操作",
              width: 340,
              render: (_, r) => (
                <Space>
                  <Select
                    size="small"
                    style={{ width: 100 }}
                    value={r.role}
                    options={ROLE_OPTIONS}
                    onChange={(role) => onChangeRole(r.id, role)}
                  />
                  <Button size="small" onClick={() => onToggleActive(r)}>
                    {r.is_active ? "停用" : "启用"}
                  </Button>
                  <Button size="small" onClick={() => setPwdUser(r)}>
                    重置密码
                  </Button>
                  <Popconfirm title="删除该员工?" onConfirm={() => onDelete(r.id)}>
                    <Button size="small" danger>
                      删除
                    </Button>
                  </Popconfirm>
                </Space>
              ),
            },
          ]}
        />
      </Card>
      <Modal
        title={`重置密码 - ${pwdUser?.username ?? ""}`}
        open={!!pwdUser}
        onCancel={() => { setPwdUser(null); pwdForm.resetFields(); }}
        onOk={() => pwdForm.submit()}
        destroyOnClose
      >
        <Form form={pwdForm} layout="vertical" onFinish={onResetPassword}>
          <Form.Item name="password" label="新密码" rules={[{ required: true, message: "请输入新密码" }]}>
            <Input.Password placeholder="新密码" />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
