import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getCrawler: vi.fn(() => Promise.resolve({ cookie: "***", proxy: "***", timeout: 20, min_delay: 0.3, max_delay: 1.0, max_retries: 4 })),
  putCrawler: vi.fn(() => Promise.resolve({})),
}));
vi.mock("../../api/crawler", () => mocks);
import CrawlerSettings from "./CrawlerSettings";

test("渲染爬虫配置页", async () => {
  render(<CrawlerSettings />);
  expect(screen.getByText("爬虫配置")).toBeInTheDocument();
  expect(screen.getByLabelText("Cookie")).toBeInTheDocument();
  expect(screen.getByLabelText("代理")).toBeInTheDocument();
  await waitFor(() => expect(mocks.getCrawler).toHaveBeenCalled());
});

test("点击保存触发 putCrawler", async () => {
  render(<CrawlerSettings />);
  await waitFor(() => expect(mocks.getCrawler).toHaveBeenCalled());
  fireEvent.click(screen.getByRole("button", { name: /保\s*存/ }));
  await waitFor(() => expect(mocks.putCrawler).toHaveBeenCalled());
});
