// 应用内自绘右键菜单的全局单例 store。
// 负责保存当前打开菜单的位置和菜单项；同一时刻只允许一个菜单实例，
// open() 直接覆盖上一次状态（对齐 confirmDialog.store.ts 的单例约束）。
import { create } from 'zustand'

export interface ContextMenuItem {
  label: string
  onClick: () => void
}

interface ContextMenuState {
  isOpen: boolean
  x: number
  y: number
  items: ContextMenuItem[]
  open: (x: number, y: number, items: ContextMenuItem[]) => void
  close: () => void
}

export const useContextMenuStore = create<ContextMenuState>((set) => ({
  isOpen: false,
  x: 0,
  y: 0,
  items: [],
  /**
   * 函数名：open
   * 入参：
   *   - x (number): 菜单弹出的横坐标（通常来自鼠标右键点击位置）
   *   - y (number): 菜单弹出的纵坐标
   *   - items (ContextMenuItem[]): 菜单项列表，每项含展示文案 label 与点击回调 onClick
   * 功能：打开（或替换）右键菜单
   * 运行逻辑：直接以传入的坐标和菜单项覆盖当前 state，isOpen 置为 true；
   *           由于是单例菜单，若已有菜单打开，本次调用会直接覆盖其位置和内容
   * 出参：无
   */
  open: (x, y, items) => set({ isOpen: true, x, y, items }),
  /**
   * 函数名：close
   * 入参：无
   * 功能：关闭右键菜单
   * 运行逻辑：将 isOpen 置为 false 并清空菜单项列表（坐标不重置，无实际影响）
   * 出参：无
   */
  close: () => set({ isOpen: false, items: [] }),
}))
