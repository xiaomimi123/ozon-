import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getImagegen: vi.fn(() =>
    Promise.resolve({
      provider: "mock",
      img_base_url: "",
      img_api_key: "***",
      img_model: "",
      fallback: "",
      img_request_template: "",
      img_response_path: "",
    })
  ),
  putImagegen: vi.fn(() => Promise.resolve({})),
}));
vi.mock("../../api/imagegen", () => mocks);
import ImagegenSettings from "./ImagegenSettings";

test("渲染 AI 生图配置页", async () => {
  render(<ImagegenSettings />);
  expect(screen.getByText("AI 生图配置")).toBeInTheDocument();
  await waitFor(() => expect(mocks.getImagegen).toHaveBeenCalled());
});

test("渲染 http 映射字段(请求体模板/响应取图点路径)", async () => {
  render(<ImagegenSettings />);
  await waitFor(() => expect(mocks.getImagegen).toHaveBeenCalled());
  expect(screen.getByText("请求体模板")).toBeInTheDocument();
  expect(screen.getByText("响应取图点路径")).toBeInTheDocument();
});

test("点击保存触发 putImagegen", async () => {
  render(<ImagegenSettings />);
  await waitFor(() => expect(mocks.getImagegen).toHaveBeenCalled());
  fireEvent.click(screen.getByRole("button", { name: /保\s*存/ }));
  await waitFor(() => expect(mocks.putImagegen).toHaveBeenCalled());
});
