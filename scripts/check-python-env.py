"""校验基线 Python 版本、虚拟环境及完整依赖锁，阻止错误环境产生误导性测试结果。"""

from __future__ import annotations

import importlib.metadata
import platform
import sys
from pathlib import Path


def read_requirements(file_path: Path, environment: dict[str, str] | None) -> list:
    """输入声明文件和可选平台环境；解析标准 requirement 并筛选条件；返回适用的声明。"""
    from packaging.requirements import Requirement

    requirements = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        requirement = Requirement(line)
        if not requirement.marker or requirement.marker.evaluate(environment):
            requirements.append(requirement)
    return requirements


def validate_dependencies(
    requirements_path: Path, lock_path: Path, environment: dict[str, str] | None = None
) -> list[str]:
    """输入直接依赖、锁文件和可选平台；检查锁定版本、安装版本及输入一致性；返回问题列表。"""
    from packaging.utils import canonicalize_name

    errors = []
    locked = {}
    for requirement in read_requirements(lock_path, environment):
        specifiers = list(requirement.specifier)
        if (
            len(specifiers) != 1
            or specifiers[0].operator != "=="
            or "*" in specifiers[0].version
        ):
            errors.append(f"requirements.lock must pin an exact version: {requirement}")
            continue
        locked[canonicalize_name(requirement.name)] = (requirement, specifiers[0].version)
        try:
            installed = importlib.metadata.version(requirement.name)
        except importlib.metadata.PackageNotFoundError:
            errors.append(f"Missing locked dependency {requirement}")
            continue
        if installed not in requirement.specifier:
            errors.append(f"Expected locked {requirement}; installed {installed}")

    # 直接声明变化时要求同步更新锁文件，包括 uvicorn[standard] 这类扩展依赖。
    for requirement in read_requirements(requirements_path, environment):
        entry = locked.get(canonicalize_name(requirement.name))
        if (
            entry is None
            or entry[1] not in requirement.specifier
            or not requirement.extras.issubset(entry[0].extras)
        ):
            errors.append(f"Update requirements.lock to match {requirement}")
    return errors


def main() -> int:
    """无参数；读取仓库版本和依赖声明并逐项核对；通过返回 0，否则输出原因并返回 1。"""
    root = Path(__file__).resolve().parent.parent
    expected = (root / ".python-version").read_text(encoding="utf-8").strip()
    errors = []
    if platform.python_version() != expected:
        errors.append(f"Python {expected} required; found {platform.python_version()}")
    if sys.prefix == sys.base_prefix:
        errors.append("Use backend/.venv; the system Python is not a baseline environment")
    try:
        errors.extend(validate_dependencies(
            root / "backend" / "requirements.txt", root / "backend" / "requirements.lock"
        ))
    except ImportError:
        errors.append("Missing packaging; install backend/requirements.lock first")
    except OSError as error:
        errors.append(str(error))
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Python {platform.python_version()} ({sys.executable})")
    print("All applicable locked dependencies and requirements.txt declarations match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
