// 应用根组件
// 职责：提供 Material-UI 主题配置，渲染主窗口组件

import { ThemeProvider, createTheme } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
import { MainWindow } from "./MainWindow";
import "./App.css";

// 创建 Material-UI 主题实例
const theme = createTheme();

/**
 * 应用根组件
 * 组件依赖关系：
 * - 被 main.tsx 引用并渲染
 * - 引用 MainWindow 组件作为主界面
 * 
 * 数据传递：
 * - 通过 ThemeProvider 向下传递主题配置
 * - MainWindow 组件通过 props 接收数据（当前无 props）
 */
function App() {
  return (
    <ThemeProvider theme={theme}>
      {/* CssBaseline 用于重置浏览器默认样式，确保跨浏览器一致性 */}
      <CssBaseline />
      {/* 渲染主窗口组件，这是应用的主要界面入口 */}
      <MainWindow />
    </ThemeProvider>
  );
}

export default App;
