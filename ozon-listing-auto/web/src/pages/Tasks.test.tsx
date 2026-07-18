import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { vi } from "vitest";
vi.mock("../api/tasks", () => ({
  listTasks: () => Promise.resolve([{ id: 1, name: "t1", listing_mode: "follow", entry_type: "keyword", provider: "mock", status: "pending", stats: null }]),
  createTask: vi.fn(), startCollect: vi.fn(), pauseCollect: vi.fn(),
}));
vi.mock("../api/category", () => ({
  getCategories: vi.fn().mockResolvedValue([{ id: 17028922, name: "Обувь", path: "Обувь", leaf: false }]),
}));
import Tasks from "./Tasks";
import { getCategories } from "../api/category";

test("展示任务列表与新建表单", async () => {
  render(<Tasks />);
  expect(screen.getByText("新建采集任务")).toBeInTheDocument();
  await waitFor(() => expect(screen.getByText("t1")).toBeInTheDocument());
});

test("入口选类目时显示类目 TreeSelect 并惰性加载 getCategories", async () => {
  render(<Tasks />);
  await waitFor(() => expect(screen.getByText("t1")).toBeInTheDocument());

  fireEvent.mouseDown(screen.getByText("关键词"));
  fireEvent.click(await screen.findByText("类目"));

  const placeholder = await screen.findByText("浏览选择类目");
  expect(placeholder).toBeInTheDocument();

  const selector = placeholder.closest(".ant-select") as HTMLElement;
  fireEvent.mouseDown(selector.querySelector(".ant-select-selector") as HTMLElement);
  fireEvent.focus(selector.querySelector("input") as HTMLElement);
  await waitFor(() => expect(getCategories).toHaveBeenCalled());
});
