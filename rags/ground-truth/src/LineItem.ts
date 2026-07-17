// 费用项数据模型
// 职责：定义单个费用项的数据结构和创建函数
// 被引用：
// - ExpenseReport.ts: 使用 LineItem 类型
// - LineItemCollection.ts: 管理 LineItem 数组
// - data.ts: 使用 createLineItem 创建初始费用项
// - CreateExpenseReportDialogBox.tsx: 使用 createLineItem 创建新费用项

/**
 * 费用项数据接口
 * 表示一个费用记录，包含：
 * - type: 费用类型（如 "Meal"、"Travel"、"Education"）
 * - description: 费用描述
 * - cost: 费用金额
 */
export interface LineItem {
  type: string;
  description: string;
  cost: number;
}

/**
 * 创建费用项的工厂函数
 * 
 * 数据传递：
 * - 接收费用项的三个字段作为参数
 * - 返回一个 LineItem 对象
 * 
 * 使用场景：
 * - 在 data.ts 中创建初始费用项
 * - 在 CreateExpenseReportDialogBox 中创建新费用项时使用默认值
 * 
 * @param type 费用类型，默认值 "(Expense type)"
 * @param description 费用描述，默认值 "(Description)"
 * @param cost 费用金额，默认值 0
 * @returns LineItem 对象
 */
export function createLineItem(
  type: string = "(Expense type)",
  description: string = "(Description)",
  cost: number = 0
): LineItem {
  return {
    type,
    description,
    cost,
  };
}

