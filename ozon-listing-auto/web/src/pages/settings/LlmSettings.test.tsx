import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getLlm: vi.fn(() => Promise.resolve({ llm_provider: "mock", llm_base_url: "", llm_api_key: "***", llm_model: "" })),
  putLlm: vi.fn(() => Promise.resolve({})),
}));
vi.mock("../../api/llm", () => mocks);
import LlmSettings from "./LlmSettings";

test("渲染 LLM 配置页", async () => {
  render(<LlmSettings />);
  expect(screen.getByText("LLM 配置")).toBeInTheDocument();
  expect(screen.getByLabelText("Provider")).toBeInTheDocument();
  expect(screen.getByLabelText("Base URL")).toBeInTheDocument();
  expect(screen.getByLabelText("Api Key")).toBeInTheDocument();
  expect(screen.getByLabelText("模型")).toBeInTheDocument();
  await waitFor(() => expect(mocks.getLlm).toHaveBeenCalled());
});

test("点击保存触发 putLlm", async () => {
  render(<LlmSettings />);
  await waitFor(() => expect(mocks.getLlm).toHaveBeenCalled());
  fireEvent.click(screen.getByRole("button", { name: /保\s*存/ }));
  await waitFor(() => expect(mocks.putLlm).toHaveBeenCalled());
});
