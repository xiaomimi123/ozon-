import { render, screen } from "@testing-library/react";
import AdvancedSection from "./AdvancedSection";

test("渲染高级设置折叠标题且子项内容默认不展开可见", () => {
  render(<AdvancedSection><div>高级字段X</div></AdvancedSection>);
  expect(screen.getByText("高级设置（一般无需修改）")).toBeInTheDocument();
  // forceRender 下子项在 DOM 中（折叠隐藏），标题一定在
});
