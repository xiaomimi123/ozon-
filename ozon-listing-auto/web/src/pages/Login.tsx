import { Form, Input, Button, Card, message } from "antd";
import { useNavigate } from "react-router-dom";
import { login } from "../api/client";

export default function Login() {
  const nav = useNavigate();
  const onFinish = async (v: { username: string; password: string }) => {
    try { await login(v.username, v.password); nav("/tasks"); }
    catch { message.error("登录失败：用户名或密码错误"); }
  };
  return (
    <div style={{ display: "flex", justifyContent: "center", paddingTop: 120 }}>
      <Card title="Ozon 跟卖/铺货系统 登录" style={{ width: 360 }}>
        <Form onFinish={onFinish} layout="vertical">
          <Form.Item name="username" label="用户名" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true }]}><Input.Password /></Form.Item>
          <Button type="primary" htmlType="submit" block>登录</Button>
        </Form>
      </Card>
    </div>
  );
}
