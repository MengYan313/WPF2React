// 应用入口文件
// 负责初始化 React 应用并挂载到 DOM

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";

// 获取根 DOM 元素并渲染应用
// StrictMode 用于在开发模式下检测潜在问题
// 组件依赖链: main.tsx -> App.tsx -> MainWindow.tsx
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
