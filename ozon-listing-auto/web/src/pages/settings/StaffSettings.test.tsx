import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { vi } from "vitest";

const mocks = vi.hoisted(() => ({
  listUsers: vi.fn(() =>
    Promise.resolve([
      { id: 1, username: "admin", role: "admin", is_active: true, created_at: "2026-01-01T00:00:00" },
      { id: 2, username: "zhangsan", role: "operator", is_active: false, created_at: "2026-01-02T00:00:00" },
    ])
  ),
  createUser: vi.fn(() => Promise.resolve({ id: 3, username: "lisi", role: "operator", is_active: true })),
  updateUser: vi.fn(() => Promise.resolve({})),
  resetPassword: vi.fn(() => Promise.resolve({})),
  deleteUser: vi.fn(() => Promise.resolve({})),
}));
vi.mock("../../api/users", () => mocks);
import StaffSettings from "./StaffSettings";

test("渲染员工列表", async () => {
  render(<StaffSettings />);
  expect(screen.getByText("员工列表")).toBeInTheDocument();
  await waitFor(() => expect(mocks.listUsers).toHaveBeenCalled());
  expect(await screen.findByText("admin")).toBeInTheDocument();
  expect(await screen.findByText("zhangsan")).toBeInTheDocument();
  expect(screen.getByText("停用")).toBeInTheDocument();
});

test("新增员工触发 createUser", async () => {
  render(<StaffSettings />);
  await waitFor(() => expect(mocks.listUsers).toHaveBeenCalled());

  fireEvent.change(screen.getByPlaceholderText("用户名"), { target: { value: "lisi" } });
  fireEvent.change(screen.getByPlaceholderText("密码"), { target: { value: "pass1234" } });
  fireEvent.click(screen.getByRole("button", { name: "新增员工" }));

  await waitFor(() =>
    expect(mocks.createUser).toHaveBeenCalledWith({ username: "lisi", password: "pass1234", role: "operator" })
  );
});
