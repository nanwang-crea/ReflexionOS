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
  open: (x, y, items) => set({ isOpen: true, x, y, items }),
  close: () => set({ isOpen: false, items: [] }),
}))
