import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { vi } from "vitest";

const mocks = vi.hoisted(() => ({
  processImages: vi.fn(() => Promise.resolve({ processed: 2, failed: 0 })),
  listImages: vi.fn(() => Promise.resolve([])),
  approveImage: vi.fn(),
  rejectImage: vi.fn(),
}));
vi.mock("../api/images", () => mocks);
import ImageStudio from "./ImageStudio";

test("渲染图片工作室页", () => {
  render(<ImageStudio />);
  expect(screen.getByText("图片工作室 ImageStudio")).toBeInTheDocument();
  expect(screen.getByText("开始改图")).toBeInTheDocument();
});

test("点击开始改图触发 processImages", async () => {
  render(<ImageStudio />);
  const input = document.querySelector("input") as HTMLInputElement;
  fireEvent.change(input, { target: { value: "1" } });
  fireEvent.click(screen.getByText("开始改图"));
  await waitFor(() => expect(mocks.processImages).toHaveBeenCalledWith(1));
});
