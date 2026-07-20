import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getSystem: vi.fn(() =>
    Promise.resolve({
      ozon_seller_provider: "mock",
      ozon_publish_dry_run: "true",
      category_tree_provider: "mock",
    })
  ),
  putSystem: vi.fn((_body: any) => Promise.resolve({})),
}));
vi.mock("../../api/system", () => mocks);
import SystemSettings from "./SystemSettings";

test("显示上品模式与试运行开关", async () => {
  render(<SystemSettings />);
  expect(await screen.findByText("上品模式")).toBeInTheDocument();
  expect(await screen.findByText(/试运行/)).toBeInTheDocument();
  await waitFor(() => expect(mocks.getSystem).toHaveBeenCalled());
});

test("保存时把 dry-run 布尔转回字符串", async () => {
  render(<SystemSettings />);
  await waitFor(() => expect(mocks.getSystem).toHaveBeenCalled());
  fireEvent.click(screen.getByRole("button", { name: /保\s*存/ }));
  await waitFor(() => expect(mocks.putSystem).toHaveBeenCalled());
  const saved = mocks.putSystem.mock.calls[0]?.[0];
  expect(saved?.ozon_publish_dry_run).toBe("true");
});

test("类目数据来源中文标签", async () => {
  render(<SystemSettings />);
  expect(await screen.findByText("类目数据来源")).toBeInTheDocument();
});
