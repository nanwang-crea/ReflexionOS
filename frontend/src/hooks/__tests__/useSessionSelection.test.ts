// 文件功能：useSessionSelection 的类型约束测试
// 文件描述：用 expectTypeOf 在编译期校验 useSessionSelection 的公开入参类型
// 恰好等于 { preferredProviderId?, preferredModelId? }，防止未来误改签名而破坏调用方约定
// 核心逻辑：通过自定义的 IsExact 类型工具做双向 extends 判断，得到严格相等（而非仅兼容）的类型断言
import { describe, expect, expectTypeOf, it } from 'vitest'
import {
  useSessionSelection,
} from '../useSessionSelection'

type Assert<T extends true> = T
type IsExact<A, B> = [A] extends [B] ? ([B] extends [A] ? true : false) : false

describe('useSessionSelection helpers', () => {
  it('accepts only preferred selection options as its public input', () => {
    type SessionSelectionOptions = Parameters<typeof useSessionSelection>[0]
    type ExpectedSessionSelectionOptions = {
      preferredProviderId?: string | null
      preferredModelId?: string | null
    }
    type SessionSelectionOptionsExact = Assert<
      IsExact<SessionSelectionOptions, ExpectedSessionSelectionOptions>
    >

    expectTypeOf<SessionSelectionOptions>().toEqualTypeOf<{
      preferredProviderId?: string | null
      preferredModelId?: string | null
    }>()
    const exactMatch: SessionSelectionOptionsExact = true
    expect(exactMatch).toBe(true)
    expect(true).toBe(true)
  })
})
