// 费用报告数据模型
// 职责：定义费用报告的数据结构和创建函数
// 被引用：data.ts 使用 createExpenseReport 创建全局 expenseData 实例

import type { LineItem } from "./LineItem";
import { LineItemCollection } from "./LineItemCollection";

/**
 * 费用报告数据接口
 * 数据结构：
 * - alias: 用户邮箱别名
 * - costCenter: 成本中心编号
 * - employeeNumber: 员工编号
 * - lineItems: 费用项集合（使用 LineItemCollection 管理）
 * - totalExpenses: 总费用（计算属性，自动计算）
 */
export interface ExpenseReport {
  alias: string;
  costCenter: string;
  employeeNumber: string;
  lineItems: LineItemCollection;
  totalExpenses: number;
}

/**
 * 创建费用报告实例的工厂函数
 * 
 * 数据传递：
 * - 接收初始参数（用户信息和费用项列表）
 * - 创建 LineItemCollection 实例管理费用项
 * - 返回包含计算属性 totalExpenses 的报告对象
 * 
 * 计算属性 totalExpenses：
 * - 使用 getter 实现，每次访问时动态计算
 * - 遍历所有费用项，累加 cost 值
 * - 当费用项变化时，totalExpenses 自动反映最新值
 * 
 * @param alias 邮箱别名，默认值 "Someone@example.com"
 * @param employeeNumber 员工编号，默认值 "57304"
 * @param costCenter 成本中心，默认值 "4032"
 * @param initialLineItems 初始费用项列表（可选）
 * @returns ExpenseReport 实例
 */
export function createExpenseReport(
  alias: string = "Someone@example.com",
  employeeNumber: string = "57304",
  costCenter: string = "4032",
  initialLineItems?: LineItem[]
): ExpenseReport {
  // 创建费用项集合，传入初始数据
  const lineItems = new LineItemCollection(initialLineItems);
  
  /**
   * 计算总费用
   * 遍历所有费用项，累加 cost 值
   */
  const calculateTotal = (): number => {
    let total = 0;
    for (const item of lineItems) {
      total += item.cost;
    }
    return total;
  };

  // 创建报告对象，使用 getter 实现计算属性
  const report = {
    alias,
    costCenter,
    employeeNumber,
    lineItems,
    // 计算属性：每次访问时动态计算总费用
    // 这样当费用项变化时，totalExpenses 总是最新的
    get totalExpenses(): number {
      return calculateTotal();
    },
  };

  return report as ExpenseReport;
}

