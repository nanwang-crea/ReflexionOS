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


@dataclass
class CodexPatch:
    """Codex-style patch - 表示单文件补丁"""
    action: str          # add/update/delete
    file_path: str
    hunks: list[list[str]]
    lines: list[str]


class CodexPatchParseError(ValueError):
    """Codex-style patch 解析错误"""
    pass


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

    def extract_file_paths(self, diff_text: str) -> list[str]:
        """从 Diff 中提取所有新文件路径"""
        paths = []
        for line in diff_text.split('\n'):
            if line.startswith('+++ '):
                path = self._normalize_file_path(line[4:].strip())
                if path and path != "/dev/null":
                    paths.append(path)
        return paths
    
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
                path = self._normalize_file_path(line[4:].strip())
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
                path = self._normalize_file_path(line[4:].strip())
                return path if path else None
        
        return None

    def _normalize_file_path(self, path: str) -> str:
        """规范化 diff 文件路径"""
        if path.startswith('b/') or path.startswith('a/'):
            return path[2:]
        return path


class CodexPatchParser:
    """Codex apply_patch 风格的单文件补丁解析器"""

    OPERATION_PREFIXES = (
        "*** Add File: ",
        "*** Update File: ",
        "*** Delete File: ",
    )

    @staticmethod
    def is_codex_style(patch_text: str) -> bool:
        return "*** Begin Patch" in patch_text

    def parse(self, patch_text: str) -> CodexPatch:
        lines = self._trim_blank_edges(patch_text.splitlines())

        if not lines or lines[0] != "*** Begin Patch":
            raise CodexPatchParseError("Codex-style patch 必须以 *** Begin Patch 开始")
        if lines[-1] != "*** End Patch":
            raise CodexPatchParseError("Codex-style patch 必须以 *** End Patch 结束")

        operation_lines = [
            line for line in lines
            if line.startswith(self.OPERATION_PREFIXES)
        ]
        if not operation_lines:
            raise CodexPatchParseError(
                "Codex-style patch 缺少文件操作头，请使用 *** Add File、*** Update File 或 *** Delete File"
            )
        if len(operation_lines) > 1:
            raise CodexPatchParseError("Codex-style patch 仅支持单文件修改")

        operation_line = operation_lines[0]
        operation_index = lines.index(operation_line)
        body = lines[operation_index + 1:-1]

        if operation_line.startswith("*** Add File: "):
            file_path = operation_line.removeprefix("*** Add File: ").strip()
            return self._parse_add_file(file_path, body)
        if operation_line.startswith("*** Update File: "):
            file_path = operation_line.removeprefix("*** Update File: ").strip()
            return self._parse_update_file(file_path, body)
        if operation_line.startswith("*** Delete File: "):
            file_path = operation_line.removeprefix("*** Delete File: ").strip()
            return self._parse_delete_file(file_path, body)

        raise CodexPatchParseError("Codex-style patch 文件操作不受支持")

    def _parse_add_file(self, file_path: str, body: list[str]) -> CodexPatch:
        if not file_path:
            raise CodexPatchParseError("Codex-style Add File 缺少文件路径")

        added_lines = []
        for line in body:
            if line == "*** End of File":
                continue
            if not line.startswith("+"):
                raise CodexPatchParseError("Codex-style Add File 内容行必须以 + 开头")
            added_lines.append(line)

        return CodexPatch(action="add", file_path=file_path, hunks=[], lines=added_lines)

    def _parse_update_file(self, file_path: str, body: list[str]) -> CodexPatch:
        if not file_path:
            raise CodexPatchParseError("Codex-style Update File 缺少文件路径")

        hunks = []
        current_hunk: list[str] | None = None

        for line in body:
            if line.startswith("*** Move to: "):
                raise CodexPatchParseError("Codex-style Move/Rename 暂不支持，请拆成新增和删除")
            if line == "*** End of File":
                continue
            if line.startswith("@@"):
                if current_hunk is not None:
                    hunks.append(current_hunk)
                current_hunk = []
                continue
            if current_hunk is None:
                raise CodexPatchParseError("Codex-style Update File 缺少 @@ hunk header")
            if not line.startswith(("+", "-", " ")):
                raise CodexPatchParseError("Codex-style hunk 行必须以空格、+ 或 - 开头")
            current_hunk.append(line)

        if current_hunk is not None:
            hunks.append(current_hunk)
        if not hunks:
            raise CodexPatchParseError("Codex-style Update File 未找到有效 hunk")

        return CodexPatch(action="update", file_path=file_path, hunks=hunks, lines=[])

    def _parse_delete_file(self, file_path: str, body: list[str]) -> CodexPatch:
        if not file_path:
            raise CodexPatchParseError("Codex-style Delete File 缺少文件路径")

        for line in body:
            if line == "*** End of File":
                continue
            raise CodexPatchParseError("Codex-style Delete File 不应包含 hunk 内容")

        return CodexPatch(action="delete", file_path=file_path, hunks=[], lines=[])

    def _trim_blank_edges(self, lines: list[str]) -> list[str]:
        start = 0
        end = len(lines)
        while start < end and lines[start] == "":
            start += 1
        while end > start and lines[end - 1] == "":
            end -= 1
        return lines[start:end]
