/**
 * 文件功能：Vite 客户端类型声明入口
 * 文件描述：引入 Vite 提供的客户端类型定义（如 import.meta.env、静态资源导入类型等），
 *          使 TypeScript 能正确识别 Vite 特有的模块和全局类型，无需手写这些类型
 * 核心逻辑：通过三斜线指令引用 vite/client 的类型声明文件，属于 Vite 项目的标准样板文件
 */
/// <reference types="vite/client" />
