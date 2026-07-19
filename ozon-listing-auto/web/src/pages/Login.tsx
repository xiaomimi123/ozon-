import { Form, Input, Button, message, Grid } from "antd";
import type { CSSProperties } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../api/client";
import { APP_NAME, APP_SUBTITLE, LOGO } from "../brand";

export default function Login() {
  const nav = useNavigate();
  const screens = Grid.useBreakpoint();
  const isMobile = !screens.md;

  const onFinish = async (v: { username: string; password: string }) => {
    try { await login(v.username, v.password); nav("/tasks"); }
    catch { message.error("登录失败：用户名或密码错误"); }
  };

  const Brand = (extra: CSSProperties) => (
    <div style={{
      background: "linear-gradient(135deg,#173a5e,#2ec4a6)", color: "#fff",
      display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
      padding: isMobile ? "32px 16px" : 48, textAlign: "center", ...extra,
    }}>
      <img src={LOGO} alt="logo" style={{ width: isMobile ? 96 : 160, borderRadius: 16, background: "#fff", padding: 8 }} />
      <h1 style={{ color: "#fff", margin: "16px 0 4px", fontSize: isMobile ? 24 : 32 }}>{APP_NAME}</h1>
      <div style={{ opacity: .85 }}>{APP_SUBTITLE}</div>
    </div>
  );

  const FormCard = (extra: CSSProperties) => (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: 24, background: "#fff", ...extra }}>
      <div style={{ width: 320, maxWidth: "100%" }}>
        <h2 style={{ marginBottom: 16 }}>登录</h2>
        <Form onFinish={onFinish} layout="vertical">
          <Form.Item name="username" label="用户名" rules={[{ required: true }]}><Input size="large" /></Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true }]}><Input.Password size="large" /></Form.Item>
          <Button type="primary" htmlType="submit" size="large" block>登录</Button>
        </Form>
      </div>
    </div>
  );

  if (isMobile) {
    // 单列：品牌条按内容高度，表单区占满剩余视口高度
    return (
      <div style={{ minHeight: "100vh", maxWidth: "100%", display: "flex", flexDirection: "column" }}>
        {Brand({ flex: "0 0 auto" })}
        {FormCard({ flex: "1 0 auto" })}
      </div>
    );
  }
  // 桌面 2:1 分栏，两栏各自填满整屏高度
  return (
    <div style={{ minHeight: "100vh", maxWidth: "100%", display: "flex" }}>
      {Brand({ flex: 2 })}
      {FormCard({ flex: 1 })}
    </div>
  );
}
