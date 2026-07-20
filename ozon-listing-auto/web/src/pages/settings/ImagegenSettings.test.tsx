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

test("显示白话标签与高级折叠", async () => {
  render(<ImagegenSettings />);
  expect(await screen.findByText("生图方式")).toBeInTheDocument();
  expect(screen.getByText("高级设置（一般无需修改）")).toBeInTheDocument();
  expect(screen.queryByText("密钥")).toBeNull();
  await waitFor(() => expect(mocks.getImagegen).toHaveBeenCalled());
});

test("选择「真实」生图方式时显示密钥/模型与请求体模板/响应取图路径字段", async () => {
  mocks.getImagegen.mockResolvedValueOnce({
    provider: "http",
    img_base_url: "",
    img_api_key: "***",
    img_model: "",
    fallback: "",
    img_request_template: "",
    img_response_path: "",
  });
  render(<ImagegenSettings />);
  expect(await screen.findByText("密钥")).toBeInTheDocument();
  expect(screen.getByText("模型名称")).toBeInTheDocument();
  expect(screen.getByText("请求体模板（JSON）")).toBeInTheDocument();
  expect(screen.getByText("响应取图路径")).toBeInTheDocument();
});

test("点击保存触发 putImagegen", async () => {
  render(<ImagegenSettings />);
  await waitFor(() => expect(mocks.getImagegen).toHaveBeenCalled());
  fireEvent.click(screen.getByRole("button", { name: /保\s*存/ }));
  await waitFor(() => expect(mocks.putImagegen).toHaveBeenCalled());
});
