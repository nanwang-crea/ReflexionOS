import os
import aiofiles
from typing import Dict, Any, List
from app.tools.base import BaseTool, ToolResult
from app.security.path_security import PathSecurity
from app.config.settings import config_manager
import logging

logger = logging.getLogger(__name__)


class FileTool(BaseTool):
    """文件操作工具 - 支持分块读取"""
    
    def __init__(self, security: PathSecurity):
        self.security = security
        self.max_lines = 200  # 默认最大读取行数
    
    @property
    def name(self) -> str:
        return "file"
    
    @property
    def description(self) -> str:
        return "文件读写和目录操作工具，支持分块读取大文件"
    
    def get_schema(self) -> Dict[str, Any]:
        """返回工具的 JSON Schema"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["read", "write", "list", "delete", "search"],
                        "description": "操作类型"
                    },
                    "path": {
                        "type": "string",
                        "description": "文件或目录路径（相对或绝对）"
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "起始行号（从1开始），用于分块读取"
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "结束行号，用于分块读取"
                    },
                    "line": {
                        "type": "integer",
                        "description": "目标行号，配合 context 使用读取周围行"
                    },
                    "context": {
                        "type": "integer",
                        "description": "上下文行数，配合 line 使用"
                    },
                    "query": {
                        "type": "string",
                        "description": "搜索关键词（search 操作）"
                    },
                    "content": {
                        "type": "string",
                        "description": "写入的内容（write 操作）"
                    }
                },
                "required": ["action", "path"]
            },
            "examples": [
                {"action": "read", "path": "README.md"},
                {"action": "read", "path": "main.py", "start_line": 1, "end_line": 50},
                {"action": "read", "path": "main.py", "line": 100, "context": 10},
                {"action": "search", "path": "main.py", "query": "def login"},
                {"action": "write", "path": "hello.py", "content": "print('hello')"},
                {"action": "list", "path": "."}
            ]
        }
    
    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        """执行文件操作"""
        action = args.get("action")
        
        try:
            if action == "read":
                return await self._read_file(args)
            elif action == "write":
                return await self._write_file(args)
            elif action == "list":
                return await self._list_directory(args)
            elif action == "delete":
                return await self._delete_file(args)
            elif action == "search":
                return await self._search_in_file(args)
            else:
                return ToolResult(
                    success=False, 
                    error=f"未知操作: {action}。支持: read, write, list, delete, search"
                )
                
        except KeyError as e:
            return ToolResult(
                success=False,
                error=f"缺少必需参数: {e}"
            )
        except Exception as e:
            logger.error(f"文件操作失败: {str(e)}")
            return ToolResult(success=False, error=str(e))
    
    async def _read_file(self, args: Dict[str, Any]) -> ToolResult:
        """读取文件内容 - 支持分块读取"""
        path = self.security.validate_path(args["path"])
        
        if not os.path.exists(path):
            return ToolResult(success=False, error=f"文件不存在: {path}")
        
        if os.path.isdir(path):
            return ToolResult(success=False, error=f"路径是目录: {path}，请使用 list 操作")
        
        # 读取文件所有行
        async with aiofiles.open(path, mode='r', encoding='utf-8') as f:
            all_lines = await f.readlines()
        
        total_lines = len(all_lines)
        
        # 确定读取范围
        start_line = args.get("start_line")
        end_line = args.get("end_line")
        line = args.get("line")
        context = args.get("context", 10)
        
        if line is not None:
            # 读取指定行周围
            start_line = max(1, line - context)
            end_line = min(total_lines, line + context)
        elif start_line is not None and end_line is not None:
            # 读取指定范围
            start_line = max(1, start_line)
            end_line = min(total_lines, end_line)
        elif start_line is not None:
            # 从 start_line 开始读取
            start_line = max(1, start_line)
            end_line = min(total_lines, start_line + self.max_lines - 1)
        else:
            # 读取全部（限制最大行数）
            if total_lines > self.max_lines:
                start_line = 1
                end_line = self.max_lines
            else:
                start_line = 1
                end_line = total_lines
        
        # 提取目标行
        selected_lines = all_lines[start_line - 1:end_line]
        
        # 构建输出
        output_lines = []
        for i, line_content in enumerate(selected_lines, start=start_line):
            output_lines.append(f"{i:4d}: {line_content.rstrip()}")
        
        content = "\n".join(output_lines)
        
        # 构建元信息
        meta = f"文件: {path}\n总行数: {total_lines}\n显示: 第 {start_line}-{end_line} 行"
        
        if total_lines > end_line:
            meta += f"\n提示: 文件还有 {total_lines - end_line} 行未显示，可使用 start_line={end_line + 1} 继续读取"
        
        logger.info(f"读取文件: {path}, 行 {start_line}-{end_line}/{total_lines}")
        
        return ToolResult(
            success=True,
            output=f"{meta}\n\n{content}",
            data={
                "content": content,
                "path": path,
                "total_lines": total_lines,
                "start_line": start_line,
                "end_line": end_line,
                "has_more": total_lines > end_line
            }
        )
    
    async def _search_in_file(self, args: Dict[str, Any]) -> ToolResult:
        """在文件中搜索内容"""
        path = self.security.validate_path(args["path"])
        query = args.get("query", "")
        
        if not os.path.exists(path):
            return ToolResult(success=False, error=f"文件不存在: {path}")
        
        if os.path.isdir(path):
            # 在目录下所有文件搜索
            return await self._search_in_directory(path, query)
        
        # 在单个文件搜索
        async with aiofiles.open(path, mode='r', encoding='utf-8') as f:
            lines = await f.readlines()
        
        matches = []
        for i, line in enumerate(lines, 1):
            if query.lower() in line.lower():
                matches.append({
                    "line": i,
                    "content": line.rstrip(),
                    "context": self._get_context(lines, i, 3)
                })
        
        if not matches:
            return ToolResult(
                success=True,
                output=f"在 {path} 中未找到 '{query}'",
                data={"matches": [], "count": 0}
            )
        
        # 格式化输出
        output_parts = [f"在 {path} 中找到 {len(matches)} 处匹配:"]
        for m in matches[:10]:  # 最多显示 10 个
            output_parts.append(f"\n第 {m['line']} 行:")
            output_parts.append(m["context"])
        
        if len(matches) > 10:
            output_parts.append(f"\n... 还有 {len(matches) - 10} 处匹配")
        
        return ToolResult(
            success=True,
            output="\n".join(output_parts),
            data={"matches": matches, "count": len(matches)}
        )
    
    def _get_context(self, lines: List[str], line_num: int, context: int) -> str:
        """获取行周围上下文"""
        start = max(0, line_num - context - 1)
        end = min(len(lines), line_num + context)
        
        context_lines = []
        for i in range(start, end):
            prefix = ">>> " if i == line_num - 1 else "    "
            context_lines.append(f"{prefix}{i + 1:4d}: {lines[i].rstrip()}")
        
        return "\n".join(context_lines)
    
    async def _search_in_directory(self, dir_path: str, query: str) -> ToolResult:
        """在目录下搜索"""
        matches = []
        
        for root, dirs, files in os.walk(dir_path):
            # 跳过隐藏目录和常见排除目录
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', 'venv']]
            
            for file in files:
                if file.startswith('.'):
                    continue
                
                file_path = os.path.join(root, file)
                
                # 只处理文本文件
                if not any(file.endswith(ext) for ext in ['.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rs', '.c', '.cpp', '.h', '.md', '.txt', '.json', '.yaml', '.yml']):
                    continue
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    
                    for i, line in enumerate(lines, 1):
                        if query.lower() in line.lower():
                            matches.append({
                                "file": file_path,
                                "line": i,
                                "content": line.rstrip()[:100]
                            })
                            
                            if len(matches) >= 50:  # 限制结果数量
                                break
                except:
                    continue
                
                if len(matches) >= 50:
                    break
            
            if len(matches) >= 50:
                break
        
        if not matches:
            return ToolResult(
                success=True,
                output=f"在 {dir_path} 中未找到 '{query}'",
                data={"matches": [], "count": 0}
            )
        
        output = f"找到 {len(matches)} 处匹配:\n"
        for m in matches[:20]:
            rel_path = os.path.relpath(m["file"], dir_path)
            output += f"\n{rel_path}:{m['line']}: {m['content']}"
        
        if len(matches) > 20:
            output += f"\n... 还有 {len(matches) - 20} 处"
        
        return ToolResult(
            success=True,
            output=output,
            data={"matches": matches, "count": len(matches)}
        )
    
    async def _write_file(self, args: Dict[str, Any]) -> ToolResult:
        """写入文件内容"""
        path = self.security.validate_write_path(args["path"])
        content = args.get("content", "")
        
        dir_path = os.path.dirname(path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        
        async with aiofiles.open(path, mode='w', encoding='utf-8') as f:
            await f.write(content)
        
        logger.info(f"写入文件: {path}")
        return ToolResult(success=True, output=f"文件已写入: {path}")
    
    async def _list_directory(self, args: Dict[str, Any]) -> ToolResult:
        """列出目录内容"""
        path = self.security.validate_path(args.get("path", "."))
        
        if not os.path.exists(path):
            return ToolResult(success=False, error=f"目录不存在: {path}")
        
        if not os.path.isdir(path):
            return ToolResult(success=False, error=f"不是目录: {path}")
        
        files: List[Dict[str, str]] = []
        for item in sorted(os.listdir(path)):
            if item.startswith('.'):
                continue
            item_path = os.path.join(path, item)
            files.append({
                "name": item,
                "type": "directory" if os.path.isdir(item_path) else "file"
            })
        
        logger.info(f"列出目录: {path}, 共 {len(files)} 项")
        return ToolResult(
            success=True, 
            output=f"目录 {path} 包含 {len(files)} 项: " + ", ".join([f"{f['name']}({'d' if f['type']=='directory' else 'f'})" for f in files[:15]]),
            data={"files": files, "path": path, "count": len(files)}
        )
    
    async def _delete_file(self, args: Dict[str, Any]) -> ToolResult:
        """删除文件"""
        path = self.security.validate_write_path(args["path"])
        
        if not os.path.exists(path):
            return ToolResult(success=False, error=f"文件不存在: {path}")
        
        if os.path.isdir(path):
            os.rmdir(path)
            logger.info(f"删除目录: {path}")
            return ToolResult(success=True, output=f"目录已删除: {path}")
        
        os.remove(path)
        logger.info(f"删除文件: {path}")
        return ToolResult(success=True, output=f"文件已删除: {path}")
