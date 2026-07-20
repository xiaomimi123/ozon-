import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getLlm: vi.fn(() => Promise.resolve({ llm_provider: "mock", llm_base_url: "", llm_api_key: "***", llm_model: "" })),
  putLlm: vi.fn(() => Promise.resolve({})),
}));
vi.mock("../../api/llm", () => mocks);
import LlmSettings from "./LlmSettings";

test("显示白话标签与高级折叠，模拟时不显密钥", async () => {
  render(<LlmSettings />);
  expect(await screen.findByText("大模型来源")).toBeInTheDocument();
  expect(screen.getByText("高级设置（一般无需修改）")).toBeInTheDocument();
  expect(screen.queryByText("密钥")).toBeNull();
  await waitFor(() => expect(mocks.getLlm).toHaveBeenCalled());
});

test("选择「真实」来源时显示密钥与模型名称字段", async () => {
  mocks.getLlm.mockResolvedValueOnce({ llm_provider: "openai", llm_base_url: "", llm_api_key: "***", llm_model: "gpt-4o-mini" });
  render(<LlmSettings />);
  expect(await screen.findByText("密钥")).toBeInTheDocument();
  expect(screen.getByText("模型名称")).toBeInTheDocument();
});

test("点击保存触发 putLlm", async () => {
  render(<LlmSettings />);
  await waitFor(() => expect(mocks.getLlm).toHaveBeenCalled());
  fireEvent.click(screen.getByRole("button", { name: /保\s*存/ }));
  await waitFor(() => expect(mocks.putLlm).toHaveBeenCalled());
});

test("provider=mock 时保存不应丢失已存的 llm_model（未挂载字段需随 store 一起提交）", async () => {
  mocks.getLlm.mockResolvedValueOnce({ llm_provider: "mock", llm_base_url: "", llm_api_key: "***", llm_model: "qwen-plus" });
  render(<LlmSettings />);
  await waitFor(() => expect(mocks.getLlm).toHaveBeenCalled());
  fireEvent.click(screen.getByRole("button", { name: /保\s*存/ }));
  await waitFor(() => expect(mocks.putLlm).toHaveBeenCalled());
  expect(mocks.putLlm).toHaveBeenCalledWith(expect.objectContaining({ llm_model: "qwen-plus" }));
});
