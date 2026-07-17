import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
vi.mock("../api/review", () => ({
  startScore: vi.fn(), getQueue: vi.fn(() => Promise.resolve({ items: [], total: 0 })),
  decide: vi.fn(), autoAdopt: vi.fn(),
}));
import ReviewBoard from "./ReviewBoard";

test("渲染审核台", () => {
  render(<ReviewBoard />);
  expect(screen.getByText("审核台")).toBeInTheDocument();
  expect(screen.getByText("开始评分")).toBeInTheDocument();
});
