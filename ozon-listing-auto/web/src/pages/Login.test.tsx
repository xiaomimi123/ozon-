import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

vi.mock("../api/client", () => ({
  login: vi.fn().mockResolvedValue({ access_token: "t", role: "admin" }),
}));

import Login from "./Login";
import { APP_NAME } from "../brand";

test("渲染登录表单", () => {
  render(<MemoryRouter><Login /></MemoryRouter>);
  // AntD Button 默认对两个汉字文案自动插入空格（"登录" -> "登 录"），故此处忽略空白比较；
  // 页面同时含有"登录"表单标题与"登录"按钮，用 role 限定为按钮
  expect(screen.getByRole("button", { name: (content) => content.replace(/\s+/g, "") === "登录" })).toBeInTheDocument();
  expect(screen.getByLabelText("用户名")).toBeInTheDocument();
  expect(screen.getByLabelText("密码")).toBeInTheDocument();
  expect(screen.getByText(APP_NAME)).toBeInTheDocument();
});
