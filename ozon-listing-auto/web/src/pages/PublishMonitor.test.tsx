import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
vi.mock("../api/pace", () => ({ getPace: vi.fn(() => Promise.resolve({})), savePace: vi.fn() }));
vi.mock("../api/publish", () => ({ schedule: vi.fn(), tick: vi.fn(), getMonitor: vi.fn(() => Promise.resolve({ counts: {}, next_scheduled_at: null })) }));
// jsdom 无 WebSocket → 提供最小桩
(globalThis as any).WebSocket = class { close() {} set onmessage(_f: any) {} set onerror(_f: any) {} };
import PublishMonitor from "./PublishMonitor";

test("渲染上架监控页", () => {
  render(<PublishMonitor />);
  expect(screen.getByText("上架监控 PublishMonitor")).toBeInTheDocument();
  expect(screen.getByText("开始排期")).toBeInTheDocument();
});
