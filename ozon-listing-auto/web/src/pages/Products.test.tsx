import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
vi.mock("../api/products", () => ({ listProducts: vi.fn(() => Promise.resolve({ items: [], total: 0 })) }));
import Products from "./Products";

test("渲染筛选表单", () => {
  render(<Products />);
  expect(screen.getByText("筛选（条件可空，可改重筛）")).toBeInTheDocument();
  expect(screen.getByText("月销≥")).toBeInTheDocument();
});
