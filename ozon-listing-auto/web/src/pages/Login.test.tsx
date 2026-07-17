import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Login from "./Login";

test("渲染登录表单", () => {
  render(<MemoryRouter><Login /></MemoryRouter>);
  // AntD Button 默认对两个汉字文案自动插入空格（"登录" -> "登 录"），故此处忽略空白比较
  expect(screen.getByText((content) => content.replace(/\s+/g, "") === "登录")).toBeInTheDocument();
  expect(screen.getByLabelText("用户名")).toBeInTheDocument();
});
