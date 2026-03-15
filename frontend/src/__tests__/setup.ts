import "@testing-library/jest-dom/vitest";

// jsdom에 없는 DOM API stub
Element.prototype.scrollIntoView = () => {};
