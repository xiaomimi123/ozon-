import { Layout as AntLayout, Menu } from "antd";
import { Outlet, useNavigate, Navigate } from "react-router-dom";
import { auth } from "../store/auth";

export default function Layout() {
  const nav = useNavigate();
  if (!auth.token) return <Navigate to="/login" replace />;
  return (
    <AntLayout style={{ minHeight: "100vh" }}>
      <AntLayout.Sider>
        <div style={{ color: "#fff", padding: 16, fontWeight: 600 }}>Ozon 系统</div>
        <Menu theme="dark" mode="inline" defaultSelectedKeys={["tasks"]}
          onClick={(e) => nav(`/${e.key}`)}
          items={[{ key: "tasks", label: "任务中心" }, { key: "products", label: "商品列表" }]} />
      </AntLayout.Sider>
      <AntLayout>
        <AntLayout.Content style={{ padding: 24 }}><Outlet /></AntLayout.Content>
      </AntLayout>
    </AntLayout>
  );
}
