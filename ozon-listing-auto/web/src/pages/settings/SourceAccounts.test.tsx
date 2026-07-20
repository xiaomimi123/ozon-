import { render, screen, within } from "@testing-library/react";
import { vi } from "vitest";
vi.mock("../../api/sourceAccounts", () => ({
  listAccounts: vi.fn(() => Promise.resolve([
    { id: 1, platform: "ali1688", label: "号1", status: "cooldown", daily_limit: 200,
      min_interval_sec: 6, daily_used_count: 3, cooldown_until: "2026-07-20T10:00:00Z", risk_hits: 1,
      created_at: "2026-07-20T09:00:00Z" },
  ])),
  createAccount: vi.fn(), updateAccount: vi.fn(), deleteAccount: vi.fn(),
}));
import SourceAccounts from "./SourceAccounts";

test("渲染货源账号表格与新增表单", async () => {
  render(<SourceAccounts />);
  expect(await screen.findByText("新增账号", { selector: ".ant-card-head-title" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "新增账号" })).toBeInTheDocument();
  expect(await screen.findByText("号1")).toBeInTheDocument();
  const table = screen.getByRole("table");
  expect(within(table).getAllByText("1688").length).toBeGreaterThanOrEqual(1); // 平台中文（表格内）
  expect(within(table).getByText("冷却中")).toBeInTheDocument();  // 状态中文
});
