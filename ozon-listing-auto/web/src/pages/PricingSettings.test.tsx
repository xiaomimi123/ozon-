import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("../api/pricing", () => ({ savePricing: vi.fn() }));

import PricingSettings from "./PricingSettings";

test("渲染定价设置页", () => {
  render(<PricingSettings />);
  expect(screen.getByText("定价设置")).toBeInTheDocument();
});
