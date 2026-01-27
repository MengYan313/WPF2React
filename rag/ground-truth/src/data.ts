// 全局数据文件
// 职责：定义和导出应用的全局共享数据
// 数据使用：
// - MainWindow.tsx: 读取和更新 expenseData、employees、costCenters
// - CreateExpenseReportDialogBox.tsx: 读取和更新 expenseData
// - ViewChartWindow.tsx: 读取 expenseData

import { createExpenseReport } from "./ExpenseReport";
import { createLineItem } from "./LineItem";

// ========== 静态数据：成本中心 ==========
// 数据用途：在 MainWindow 中作为下拉选择框的选项
export interface CostCenter {
  number: string;
  name: string;
}

export const costCenters: CostCenter[] = [
  { number: "4032", name: "Sales" },
  { number: "4034", name: "Marketing" },
  { number: "5061", name: "Human Resources" },
  { number: "5062", name: "Research and Development" },
];

// ========== 静态数据：员工列表 ==========
// 数据用途：在 MainWindow 中根据员工类型筛选显示
export interface Employee {
  name: string;
  type: string;
  employeeNumber: string;
}

export const employees: Employee[] = [
  { name: "Terry Adams", type: "FTE", employeeNumber: "1" },
  { name: "Claire O'Donnell", type: "FTE", employeeNumber: "12345" },
  { name: "Palle Peterson", type: "FTE", employeeNumber: "5678" },
  { name: "Amy E. Alberts", type: "CSG", employeeNumber: "99222" },
  { name: "Stefan Hesse", type: "Vendor", employeeNumber: "-" },
];

// ========== 全局费用报告实例 ==========
// 这是应用的核心共享状态，多个组件都会读取和修改它
// 
// 数据传递机制：
// 1. MainWindow 通过 useState 和 useEffect 同步 alias、employeeNumber、costCenter
// 2. CreateExpenseReportDialogBox 直接读取和修改 expenseData.lineItems
// 3. ViewChartWindow 直接读取 expenseData.lineItems 和 totalExpenses
// 
// 数据流：
// - MainWindow 修改表单 -> 同步到 expenseData -> CreateExpenseReportDialogBox 读取显示
// - CreateExpenseReportDialogBox 编辑费用项 -> 更新 expenseData.lineItems -> 触发观察者 -> ViewChartWindow 自动更新
// 
// 初始化数据：包含默认的用户信息和 5 个示例费用项
export const expenseData = createExpenseReport(
  "Someone@example.com",
  "57304",
  "4032",
  [
    createLineItem("Meal", "Mexican Lunch", 12),
    createLineItem("Meal", "Italian Dinner", 45),
    createLineItem("Education", "Developer Conference", 90),
    createLineItem("Travel", "Taxi", 70),
    createLineItem("Travel", "Hotel", 60),
  ]
);

