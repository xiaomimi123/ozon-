import "@testing-library/jest-dom";

// jsdom 未实现 window.matchMedia，AntD 的 Grid/断点 Hook 依赖它，测试环境下需 polyfill。
if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }) as unknown as MediaQueryList;
}
