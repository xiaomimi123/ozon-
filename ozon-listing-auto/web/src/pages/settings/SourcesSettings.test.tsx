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
      import_token: "",
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

test("端点可见+高级折叠存在", async () => {
  render(<SourcesSettings />);
  expect(await screen.findByText("1688 图搜接口地址")).toBeInTheDocument();
  expect(screen.getByText("高级设置（一般无需修改）")).toBeInTheDocument();
});

test("渲染关键字段(图搜地址/关键词地址/请求方法/额外参数/响应路径)", async () => {
  render(<SourcesSettings />);
  await waitFor(() => expect(mocks.getSources).toHaveBeenCalled());
  expect(screen.getByText("1688 图搜接口地址")).toBeInTheDocument();
  expect(screen.getByText("1688 关键词搜索接口地址")).toBeInTheDocument();
  expect(screen.getByText("请求方法")).toBeInTheDocument();
  expect(screen.getByText("额外请求参数（JSON）")).toBeInTheDocument();
  expect(screen.getByText("额外请求头（JSON）")).toBeInTheDocument();
  expect(screen.getByText("响应商品列表路径")).toBeInTheDocument();
});

test("点击保存触发 putSources", async () => {
  render(<SourcesSettings />);
  await waitFor(() => expect(mocks.getSources).toHaveBeenCalled());
  fireEvent.click(screen.getByRole("button", { name: /保\s*存/ }));
  await waitFor(() => expect(mocks.putSources).toHaveBeenCalled());
});

test("显示采集令牌字段与高级折叠内的解析路径字段", async () => {
  mocks.getSources.mockResolvedValueOnce({
    ali1688_image_search_url: "", ali1688_keyword_search_url: "", ali1688_method: "GET",
    ali1688_extra_params: "", ali1688_extra_headers: "", ali1688_offer_list_path: "data.offerList",
    import_token: "***",
  });
  render(<SourcesSettings />);
  expect(await screen.findByText("采集令牌")).toBeInTheDocument();
  expect(screen.getByText("商品列表路径")).toBeInTheDocument();
  expect(screen.getByText("标题路径")).toBeInTheDocument();
  expect(screen.getByText("价格路径")).toBeInTheDocument();
});
