/**
 * Vitest 全局测试初始化文件。
 *
 * 作用：happy-dom 20.x 默认不再提供 localStorage/sessionStorage 实现，
 * 但项目多个 zustand store 使用 persist 中间件、依赖全局 localStorage，
 * 在测试环境下会因 storage 未定义而报错（Cannot read properties of undefined）。
 * 这里注入一个基于内存的 Storage polyfill，挂到 window 和 globalThis 上，
 * 让 persist store 在测试中可以正常读写，且每个用例之间互不污染。
 */
import { beforeEach } from 'vitest'

/**
 * 创建一个符合 Web Storage 接口的内存实现。
 * 输入：无
 * 作用：用一个普通对象模拟 localStorage 的键值存储与标准方法
 * 返回：实现了 getItem/setItem/removeItem/clear/key/length 的对象
 */
function createMemoryStorage(): Storage {
  let store: Record<string, string> = {}
  return {
    get length() {
      return Object.keys(store).length
    },
    clear() {
      store = {}
    },
    getItem(key: string) {
      return Object.prototype.hasOwnProperty.call(store, key) ? store[key] : null
    },
    key(index: number) {
      return Object.keys(store)[index] ?? null
    },
    removeItem(key: string) {
      delete store[key]
    },
    setItem(key: string, value: string) {
      store[key] = String(value)
    },
  } as Storage
}

// 将内存 storage 挂到全局与 window，覆盖 happy-dom 缺失的实现
const memoryLocalStorage = createMemoryStorage()
const memorySessionStorage = createMemoryStorage()

Object.defineProperty(globalThis, 'localStorage', {
  value: memoryLocalStorage,
  writable: true,
  configurable: true,
})
Object.defineProperty(globalThis, 'sessionStorage', {
  value: memorySessionStorage,
  writable: true,
  configurable: true,
})

if (typeof window !== 'undefined') {
  Object.defineProperty(window, 'localStorage', {
    value: memoryLocalStorage,
    writable: true,
    configurable: true,
  })
  Object.defineProperty(window, 'sessionStorage', {
    value: memorySessionStorage,
    writable: true,
    configurable: true,
  })
}

// 每个用例前清空，保证 store 持久化状态不跨用例泄漏
beforeEach(() => {
  memoryLocalStorage.clear()
  memorySessionStorage.clear()
})
