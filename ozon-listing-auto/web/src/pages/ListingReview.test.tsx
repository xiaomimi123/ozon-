import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
vi.mock("../api/listing", () => ({
  buildDrafts: vi.fn(), getDrafts: vi.fn(() => Promise.resolve([])), confirmDraft: vi.fn(),
  autoConfirm: vi.fn(), publishDrafts: vi.fn(),
}));
vi.mock("../api/shops", () => ({ listShops: vi.fn(() => Promise.resolve([])) }));
import ListingReview from "./ListingReview";

test("渲染上架审核页", () => {
  render(<ListingReview />);
  expect(screen.getByText("上架审核(跟卖草稿)")).toBeInTheDocument();
  expect(screen.getByText("生成草稿")).toBeInTheDocument();
});
