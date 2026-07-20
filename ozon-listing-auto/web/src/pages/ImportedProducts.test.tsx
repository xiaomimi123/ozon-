import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
vi.mock("../api/importer", () => ({
  listImported: vi.fn(() => Promise.resolve([
    { id: 1, platform: "ali1688", offer_id: "A1", title: "连衣裙", price: 18.5, image_url: "u",
      shop_name: "甲店", detail_url: "d", sales: 300, created_at: "2026-07-20T10:00:00Z" },
  ])),
  listCaptures: vi.fn(() => Promise.resolve([])), getCapture: vi.fn(),
}));
import ImportedProducts from "./ImportedProducts";
test("渲染导入商品表格", async () => {
  render(<ImportedProducts />);
  expect(await screen.findByText("连衣裙")).toBeInTheDocument();
  expect(await screen.findByText("甲店")).toBeInTheDocument();
});
