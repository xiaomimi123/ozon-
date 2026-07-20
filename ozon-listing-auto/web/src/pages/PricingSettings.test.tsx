import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("../api/pricing", () => ({ savePricing: vi.fn() }));

import PricingSettings from "./PricingSettings";

test("渲染定价设置页", () => {
  render(<PricingSettings />);
  expect(screen.getByText("定价设置")).toBeInTheDocument();
});

test("常用项可见+高级折叠存在", async () => {
  render(<PricingSettings />);
  expect(await screen.findByText("定价模式")).toBeInTheDocument();
  expect(screen.getByText("高级设置（一般无需修改）")).toBeInTheDocument();
});
