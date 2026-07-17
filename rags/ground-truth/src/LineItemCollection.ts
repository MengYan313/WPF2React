// 费用项集合类 - 简化版
// 职责：管理费用项列表，提供简单的增删改查功能
import type { LineItem } from "./LineItem";

/**
 * 费用项集合类
 * 简化实现：直接使用数组，移除观察者模式，由 React 组件管理状态更新
 */
export class LineItemCollection {
  private items: LineItem[] = [];

  constructor(initialItems?: LineItem[]) {
    if (initialItems) {
      this.items = [...initialItems];
    }
  }

  add(item: LineItem): void {
    this.items.push(item);
  }

  remove(item: LineItem): void {
    const index = this.items.indexOf(item);
    if (index > -1) {
      this.items.splice(index, 1);
    }
  }

  update(index: number, item: LineItem): void {
    if (index >= 0 && index < this.items.length) {
      this.items[index] = item;
    }
  }

  getItem(index: number): LineItem | undefined {
    return this.items[index];
  }

  getItems(): LineItem[] {
    return [...this.items];
  }

  get length(): number {
    return this.items.length;
  }

  [Symbol.iterator](): Iterator<LineItem> {
    return this.items[Symbol.iterator]();
  }
}

