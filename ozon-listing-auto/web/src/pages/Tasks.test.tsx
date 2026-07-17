import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
vi.mock("../api/tasks", () => ({
  listTasks: () => Promise.resolve([{ id: 1, name: "t1", listing_mode: "follow", entry_type: "keyword", provider: "mock", status: "pending", stats: null }]),
  createTask: vi.fn(), startCollect: vi.fn(), pauseCollect: vi.fn(),
}));
import Tasks from "./Tasks";

test("展示任务列表与新建表单", async () => {
  render(<Tasks />);
  expect(screen.getByText("新建采集任务")).toBeInTheDocument();
  await waitFor(() => expect(screen.getByText("t1")).toBeInTheDocument());
});
