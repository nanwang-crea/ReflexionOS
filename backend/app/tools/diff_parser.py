import re
from dataclasses import dataclass


@dataclass
class Hunk:
    """Diff Hunk - 表示一个修改块"""
    old_start: int      # 原文件起始行号
    old_count: int      # 原文件行数
    new_start: int      # 新文件起始行号
    new_count: int      # 新文件行数
    lines: list[str]    # Hunk内容 (+/-/ 开头)


class DiffParser:
    """Unified Diff 解析器"""
    
    def parse(self, diff_text: str) -> list[Hunk]:
        """
        解析 Unified Diff 格式
        
        Args:
            diff_text: Unified Diff 文本
            
        Returns:
            List[Hunk]: 解析出的 Hunk 列表
        """
        hunks = []
        lines = diff_text.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # 查找 hunk 头: @@ -old_start,old_count +new_start,new_count @@
            if line.startswith('@@'):
                match = re.match(r'@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@', line)
                if match:
                    hunk = Hunk(
                        old_start=int(match.group(1)),
                        old_count=int(match.group(2) or 1),
                        new_start=int(match.group(3)),
                        new_count=int(match.group(4) or 1),
                        lines=[]
                    )
                    
                    # 收集 hunk 内容
                    i += 1
                    while i < len(lines) and not lines[i].startswith('@@'):
                        if lines[i].startswith(('+', '-', ' ')):
                            hunk.lines.append(lines[i])
                        i += 1
                    
                    hunks.append(hunk)
                else:
                    i += 1
            else:
                i += 1
        
        return hunks
    
    def extract_file_path(self, diff_text: str) -> str | None:
        """
        从 Diff 中提取文件路径
        
        Args:
            diff_text: Unified Diff 文本
            
        Returns:
            Optional[str]: 文件路径,如果无法提取返回 None
        """
        lines = diff_text.split('\n')
        
        for line in lines:
            # 查找 +++ b/path/to/file
            if line.startswith('+++ '):
                path = line[4:].strip()
                # 移除 b/ 前缀
                if path.startswith('b/') or path.startswith('a/'):
                    path = path[2:]
                return path if path else None
        
        return None
    
    def extract_old_file_path(self, diff_text: str) -> str | None:
        """
        从 Diff 中提取原文件路径
        
        Args:
            diff_text: Unified Diff 文本
            
        Returns:
            Optional[str]: 原文件路径
        """
        lines = diff_text.split('\n')
        
        for line in lines:
            # 查找 --- a/path/to/file
            if line.startswith('--- '):
                path = line[4:].strip()
                # 移除 a/ 前缀
                if path.startswith('a/') or path.startswith('b/'):
                    path = path[2:]
                return path if path else None
        
        return None
