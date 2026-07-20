import { Collapse } from "antd";
import type { ReactNode } from "react";

export default function AdvancedSection({ children }: { children: ReactNode }) {
  return (
    <Collapse
      ghost
      style={{ marginBottom: 8 }}
      items={[{ key: "adv", label: "高级设置（一般无需修改）", forceRender: true, children }]}
    />
  );
}
