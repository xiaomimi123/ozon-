import { Layout as AntLayout, Menu, Button } from "antd";
import { Outlet, useNavigate, Navigate } from "react-router-dom";
import { auth } from "../store/auth";
import { APP_NAME, LOGO } from "../brand";

const menuItems: { key: string; label: string; adminOnly?: boolean }[] = [
  { key: "tasks", label: "任务中心" },
  { key: "products", label: "商品列表" },
  { key: "review", label: "审核台" },
  { key: "listing", label: "上架审核" },
  { key: "image-studio", label: "图片工作室" },
  { key: "monitor", label: "上架监控" },
  { key: "shops", label: "店铺管理", adminOnly: true },
  { key: "pricing", label: "定价设置", adminOnly: true },
  { key: "settings/imagegen", label: "AI 生图配置", adminOnly: true },
  { key: "settings/crawler", label: "爬虫配置", adminOnly: true },
  { key: "settings/llm", label: "LLM 配置", adminOnly: true },
  { key: "settings/sources", label: "货源配置", adminOnly: true },
  { key: "settings/system", label: "系统设置", adminOnly: true },
  { key: "staff", label: "员工管理", adminOnly: true },
];

export default function Layout() {
  const nav = useNavigate();
  if (!auth.token) return <Navigate to="/login" replace />;
  const role = auth.role;
  const items = menuItems.filter((i) => !i.adminOnly || role === "admin");
  const onLogout = () => { auth.clear(); nav("/login"); };
  return (
    <AntLayout style={{ minHeight: "100vh" }}>
      <AntLayout.Sider>
        <div style={{ color: "#fff", padding: 16, display: "flex", alignItems: "center", gap: 8 }}>
          <img src={LOGO} alt="logo" style={{ width: 28, height: 28, borderRadius: 6, background: "#fff" }} />
          <span style={{ fontWeight: 600 }}>{APP_NAME}</span>
        </div>
        <Menu theme="dark" mode="inline" defaultSelectedKeys={["tasks"]}
          onClick={(e) => nav(`/${e.key}`)}
          items={items} />
        <div style={{ padding: 16 }}>
          <Button type="text" onClick={onLogout} style={{ color: "rgba(255,255,255,.85)", width: "100%", textAlign: "left" }}>
            退出登录
          </Button>
        </div>
      </AntLayout.Sider>
      <AntLayout>
        <AntLayout.Content style={{ padding: 24 }}><Outlet /></AntLayout.Content>
      </AntLayout>
    </AntLayout>
  );
}
