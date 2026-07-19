import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getSources: vi.fn(() =>
    Promise.resolve({
      ali1688_image_search_url: "",
      ali1688_keyword_search_url: "",
      ali1688_method: "GET",
      ali1688_extra_params: "",
      ali1688_extra_headers: "",
      ali1688_offer_list_path: "data.offerList",
    })
  ),
  putSources: vi.fn(() => Promise.resolve({})),
}));
vi.mock("../../api/sources", () => mocks);
import SourcesSettings from "./SourcesSettings";

test("渲染货源配置页", async () => {
  render(<SourcesSettings />);
  expect(screen.getByText("货源配置")).toBeInTheDocument();
  await waitFor(() => expect(mocks.getSources).toHaveBeenCalled());
});

test("渲染关键字段(图搜端点/请求方法/额外参数/响应路径)", async () => {
  render(<SourcesSettings />);
  await waitFor(() => expect(mocks.getSources).toHaveBeenCalled());
  expect(screen.getByText("图搜端点(image_search_url)")).toBeInTheDocument();
  expect(screen.getByText("关键词搜索端点(keyword_search_url)")).toBeInTheDocument();
  expect(screen.getByText("请求方法")).toBeInTheDocument();
  expect(screen.getByText("额外请求参数(JSON)")).toBeInTheDocument();
  expect(screen.getByText("额外请求头(JSON)")).toBeInTheDocument();
  expect(screen.getByText("响应 offerList 点路径")).toBeInTheDocument();
});

test("点击保存触发 putSources", async () => {
  render(<SourcesSettings />);
  await waitFor(() => expect(mocks.getSources).toHaveBeenCalled());
  fireEvent.click(screen.getByRole("button", { name: /保\s*存/ }));
  await waitFor(() => expect(mocks.putSources).toHaveBeenCalled());
});
