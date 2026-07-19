import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { vi } from "vitest";
import { message } from "antd";
const draftRow = { id: 1, mode: "create", status: "draft", title: "T", cost: 1, price: 2, margin: 0.1, stock_qty: 1 };
vi.mock("../api/listing", () => ({
  buildDrafts: vi.fn(), getDrafts: vi.fn(() => Promise.resolve([])), confirmDraft: vi.fn(),
  autoConfirm: vi.fn(), publishDrafts: vi.fn(),
}));
vi.mock("../api/shops", () => ({ listShops: vi.fn(() => Promise.resolve([])) }));
vi.mock("../api/category", () => ({
  getCategories: vi.fn(() => Promise.resolve([])), suggestCategory: vi.fn(), confirmCategory: vi.fn(),
}));
vi.mock("../api/ozonCatalog", () => ({
  getTypes: vi.fn(() => Promise.resolve([])),
  getAttributes: vi.fn(() => Promise.resolve([])),
  getAttributeValues: vi.fn(() => Promise.resolve([])),
  confirmCreateFields: vi.fn(() => Promise.resolve({ ok: true })),
}));
import ListingReview from "./ListingReview";
import { getDrafts, confirmDraft } from "../api/listing";

test("渲染上架审核页", () => {
  render(<ListingReview />);
  expect(screen.getByText("上架审核(跟卖草稿)")).toBeInTheDocument();
  expect(screen.getByText("生成草稿")).toBeInTheDocument();
});

test("确认草稿返回 error 时不误报已确认", async () => {
  (getDrafts as ReturnType<typeof vi.fn>).mockResolvedValue([draftRow]);
  (confirmDraft as ReturnType<typeof vi.fn>).mockResolvedValue({
    draft_id: 1, status: "draft", error: "自建草稿需先确认类目与图片再确认上架",
  });
  const successSpy = vi.spyOn(message, "success");
  const warningSpy = vi.spyOn(message, "warning");
  render(<ListingReview />);
  const taskInput = screen.getByRole("spinbutton");
  fireEvent.change(taskInput, { target: { value: "1" } });
  fireEvent.click(screen.getByText(/刷\s*新/));
  const confirmBtn = await screen.findByText("确认草稿");
  fireEvent.click(confirmBtn);

  await waitFor(() => expect(confirmDraft).toHaveBeenCalledWith(1));
  await waitFor(() => expect(warningSpy).toHaveBeenCalledWith("自建草稿需先确认类目与图片再确认上架"));
  expect(successSpy).not.toHaveBeenCalledWith("已确认");

  successSpy.mockRestore();
  warningSpy.mockRestore();
});

test("自建草稿显示补充信息入口", async () => {
  (getDrafts as ReturnType<typeof vi.fn>).mockResolvedValue([
    { id: 1, mode: "create", title: "自建品", category_id: 100, status: "draft" },
  ]);
  render(<ListingReview />);
  const taskInput = screen.getByRole("spinbutton");
  fireEvent.change(taskInput, { target: { value: "1" } });
  fireEvent.click(screen.getByText(/刷\s*新/));
  expect(await screen.findByText(/补充信息/)).toBeInTheDocument();
});
