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
          items={[{ key: "tasks", label: "任务中心" }, { key: "products", label: "商品列表" }, { key: "review", label: "审核台" }, { key: "listing", label: "上架审核" }, { key: "image-studio", label: "图片工作室" }, { key: "shops", label: "店铺管理" }, { key: "pricing", label: "定价设置" }, { key: "settings/imagegen", label: "AI 生图配置" }, { key: "settings/crawler", label: "爬虫配置" }, { key: "settings/system", label: "系统设置" }, { key: "monitor", label: "上架监控" }]} />
      </AntLayout.Sider>
      <AntLayout>
        <AntLayout.Content style={{ padding: 24 }}><Outlet /></AntLayout.Content>
      </AntLayout>
    </AntLayout>
  );
}
