import { useState } from "react";
import { Layout as AntLayout, Menu, Button, Drawer, Grid } from "antd";
import { Outlet, useNavigate, useLocation, Navigate } from "react-router-dom";
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
  const loc = useLocation();
  const screens = Grid.useBreakpoint();
  const isMobile = !screens.md;
  const [drawerOpen, setDrawerOpen] = useState(false);
  if (!auth.token) return <Navigate to="/login" replace />;
  const role = auth.role;
  const items = menuItems.filter((i) => !i.adminOnly || role === "admin");
  const selectedKey = loc.pathname.replace(/^\//, "") || "tasks";
  const onLogout = () => { auth.clear(); nav("/login"); };

  const BrandHead = (
    <div style={{ color: "#fff", padding: 16, display: "flex", alignItems: "center", gap: 8 }}>
      <img src={LOGO} alt="logo" style={{ width: 28, height: 28, borderRadius: 6, background: "#fff" }} />
      <span style={{ fontWeight: 600 }}>{APP_NAME}</span>
    </div>
  );

  // 侧栏/抽屉共用的导航内容
  const NavBody = (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {BrandHead}
      <Menu theme="dark" mode="inline" selectedKeys={[selectedKey]} style={{ flex: 1, borderInlineEnd: 0 }}
        onClick={(e) => { nav(`/${e.key}`); setDrawerOpen(false); }}
        items={items} />
      <div style={{ padding: 16 }}>
        <Button type="text" onClick={onLogout} style={{ color: "rgba(255,255,255,.85)", width: "100%", textAlign: "left" }}>
          退出登录
        </Button>
      </div>
    </div>
  );

  if (isMobile) {
    return (
      <AntLayout style={{ minHeight: "100vh" }}>
        <AntLayout.Header style={{ display: "flex", alignItems: "center", gap: 12, padding: "0 16px", background: "#001529" }}>
          <Button type="text" onClick={() => setDrawerOpen(true)}
            style={{ color: "#fff", fontSize: 20, lineHeight: 1 }} aria-label="菜单">☰</Button>
          <img src={LOGO} alt="logo" style={{ width: 24, height: 24, borderRadius: 6, background: "#fff" }} />
          <span style={{ color: "#fff", fontWeight: 600 }}>{APP_NAME}</span>
        </AntLayout.Header>
        <Drawer placement="left" open={drawerOpen} onClose={() => setDrawerOpen(false)}
          width={220} styles={{ body: { padding: 0, background: "#001529" }, header: { display: "none" } }}>
          {NavBody}
        </Drawer>
        <AntLayout.Content style={{ padding: 16, overflowX: "auto" }}><Outlet /></AntLayout.Content>
      </AntLayout>
    );
  }

  return (
    <AntLayout style={{ minHeight: "100vh" }}>
      <AntLayout.Sider>{NavBody}</AntLayout.Sider>
      <AntLayout>
        <AntLayout.Content style={{ padding: 24 }}><Outlet /></AntLayout.Content>
      </AntLayout>
    </AntLayout>
  );
}
