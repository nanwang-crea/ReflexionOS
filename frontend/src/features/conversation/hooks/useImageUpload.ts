/**
 * 文件功能：图片附件的待上传状态管理与上传流程封装（自定义 hook）
 * 文件描述：管理用户在聊天输入框中选择的图片附件（预览、移除、清空），在真正发送前
 *          对超大图片做压缩，再逐个上传到当前会话，返回后端生成的附件 id 列表。
 * 核心逻辑：
 *   1. 附件仅保存在组件状态中（不会自动上传），发送消息时才调用 uploadAll 触发上传；
 *   2. 图片超过 COMPRESS_THRESHOLD 才会被压缩（限制最大边长、转码为 jpeg），
 *      避免占用带宽和后端存储；
 *   3. 所有 object URL（用于本地预览）在附件移除/清空/会话切换时主动 revoke，防止内存泄漏。
 */
import { useCallback, useEffect, useState } from 'react'

// 待上传的图片附件：本地生成的 id、原始 File 对象、用于预览的 object URL
export interface PendingAttachment {
  id: string
  file: File
  previewUrl: string
}

const MAX_FILE_SIZE = 10 * 1024 * 1024 // 单张图片最大允许大小：10MB
const MAX_DIMENSION = 2048 // 压缩时图片长/宽的最大像素限制
const COMPRESS_THRESHOLD = 1024 * 1024 // 超过该大小（1MB）才触发压缩

/**
 * 函数名：compressImage
 * 入参：
 *   - file (File): 待处理的图片文件
 * 功能：当图片超过压缩阈值时，按最大边长限制缩放并转码为 jpeg 以减小体积
 * 运行逻辑：
 *   1. 若文件大小未超过 COMPRESS_THRESHOLD，直接原样返回；
 *   2. 否则加载图片到 <img>，按 MAX_DIMENSION 计算等比缩放后的宽高；
 *   3. 用 canvas 绘制缩放后的图像，再通过 toBlob 输出为 jpeg 格式（质量 0.8）；
 *   4. 任意步骤失败（无 2d 上下文、toBlob 失败、图片加载失败）均回退为返回原始文件，
 *      保证上传流程不会因压缩失败而中断。
 * 出参：Promise<File> - 压缩后的文件（或压缩失败/无需压缩时的原始文件）
 */
async function compressImage(file: File): Promise<File> {
  if (file.size <= COMPRESS_THRESHOLD) {
    return file
  }

  return new Promise((resolve) => {
    const img = new Image()
    const url = URL.createObjectURL(file)

    img.onload = () => {
      URL.revokeObjectURL(url)

      let { width, height } = img
      if (width > MAX_DIMENSION || height > MAX_DIMENSION) {
        const ratio = Math.min(MAX_DIMENSION / width, MAX_DIMENSION / height)
        width = Math.round(width * ratio)
        height = Math.round(height * ratio)
      }

      const canvas = document.createElement('canvas')
      canvas.width = width
      canvas.height = height
      const ctx = canvas.getContext('2d')
      if (!ctx) {
        resolve(file)
        return
      }

      ctx.drawImage(img, 0, 0, width, height)
      canvas.toBlob(
        (blob) => {
          if (!blob) {
            resolve(file)
            return
          }
          const compressed = new File([blob], file.name.replace(/\.[^.]+$/, '.jpg'), {
            type: 'image/jpeg',
            lastModified: Date.now(),
          })
          resolve(compressed)
        },
        'image/jpeg',
        0.8
      )
    }

    img.onerror = () => {
      URL.revokeObjectURL(url)
      resolve(file)
    }

    img.src = url
  })
}

/**
 * 函数名：uploadFile
 * 入参：
 *   - sessionId (string): 目标会话 id
 *   - file (File): 待上传的文件（通常是压缩后的图片）
 * 功能：将单个文件以 multipart/form-data 形式上传到指定会话的上传接口
 * 运行逻辑：构造 FormData 并 POST 到 /api/sessions/{sessionId}/upload；
 *          若响应非 2xx，尝试解析错误详情并抛出异常，否则解析并返回 JSON 结果
 * 出参：Promise<{ attachment_id: string }> - 后端生成的附件 id
 */
async function uploadFile(
  sessionId: string,
  file: File,
): Promise<{ attachment_id: string }> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`/api/sessions/${sessionId}/upload`, {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: '上传失败' }))
    throw new Error(error.detail || '上传失败')
  }

  return response.json()
}

/**
 * 函数名：useImageUpload
 * 入参：
 *   - sessionId (string | null): 当前会话 id，为 null 时表示尚未确定会话
 * 功能：提供图片附件的本地状态管理与批量上传能力，供聊天输入框组件使用
 * 运行逻辑：
 *   1. 内部维护 attachments 状态（PendingAttachment 数组）；
 *   2. addFiles 校验文件类型（仅接受 image/*）与大小上限，超限则抛错，否则加入待上传列表；
 *   3. removeAttachment/clearAttachments 移除附件时同步释放对应的 object URL；
 *   4. uploadAll 遍历所有附件，逐个压缩后调用 uploadFile 上传，收集返回的附件 id；
 *      单个附件上传失败会立即抛出带文件名的错误信息，中断后续上传；
 *   5. sessionId 变化时（会话切换/卸载），通过 useEffect 清理函数清空附件并释放所有预览 URL，
 *      避免旧会话的图片残留到新会话。
 * 出参：{ attachments, addFiles, removeAttachment, clearAttachments, uploadAll, hasAttachments }
 *      - 附件状态与操作方法的集合，供调用组件直接使用
 */
export function useImageUpload(sessionId: string | null) {
  const [attachments, setAttachments] = useState<PendingAttachment[]>([])

  // 切换会话时清空待上传附件，避免在 A 会话暂存的图片残留并误传到 B 会话。
  // 同时释放预览用的 object URL，防止内存泄漏。
  useEffect(() => {
    return () => {
      setAttachments((prev) => {
        prev.forEach((attachment) => {
          if (attachment.previewUrl) {
            URL.revokeObjectURL(attachment.previewUrl)
          }
        })
        return []
      })
    }
  }, [sessionId])

  // 添加文件：过滤出图片类型，校验大小上限后生成待上传附件（含本地预览 URL）
  const addFiles = useCallback((files: File[]) => {
    const imageFiles = files.filter((f) => f.type.startsWith('image/'))
    if (imageFiles.length === 0) return

    const oversized = imageFiles.filter((f) => f.size > MAX_FILE_SIZE)
    if (oversized.length > 0) {
      throw new Error(`图片大小超过限制（最大 10MB）：${oversized.map((f) => f.name).join(', ')}`)
    }

    const newAttachments: PendingAttachment[] = imageFiles.map((file) => ({
      id: crypto.randomUUID(),
      file,
      previewUrl: URL.createObjectURL(file),
    }))

    setAttachments((prev) => [...prev, ...newAttachments])
  }, [])

  // 移除单个附件：释放对应预览 URL，避免内存泄漏
  const removeAttachment = useCallback((id: string) => {
    setAttachments((prev) => {
      const target = prev.find((a) => a.id === id)
      if (target?.previewUrl) {
        URL.revokeObjectURL(target.previewUrl)
      }
      return prev.filter((a) => a.id !== id)
    })
  }, [])

  // 清空所有附件：批量释放全部预览 URL
  const clearAttachments = useCallback(() => {
    setAttachments((prev) => {
      prev.forEach((a) => {
        if (a.previewUrl) URL.revokeObjectURL(a.previewUrl)
      })
      return []
    })
  }, [])

  // 批量上传：逐个压缩+上传附件，返回后端附件 id 列表；无会话或无附件时直接返回空数组
  const uploadAll = useCallback(async (): Promise<string[]> => {
    if (!sessionId || attachments.length === 0) return []

    const uploadedIds: string[] = []

    for (const attachment of attachments) {
      try {
        const compressed = await compressImage(attachment.file)
        const result = await uploadFile(sessionId, compressed)
        uploadedIds.push(result.attachment_id)
      } catch (err) {
        const msg = err instanceof Error ? err.message : '上传失败'
        throw new Error(`图片 ${attachment.file.name} 上传失败: ${msg}`)
      }
    }

    return uploadedIds
  }, [sessionId, attachments])

  return {
    attachments,
    addFiles,
    removeAttachment,
    clearAttachments,
    uploadAll,
    hasAttachments: attachments.length > 0,
  }
}
