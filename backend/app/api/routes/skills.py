# 文件功能：技能（Skill）管理相关的 API 路由
# 文件描述：提供技能的分页查询、分类查询、刷新扫描、安装、删除、详情查看、启用/禁用接口
# 核心逻辑：技能数据统一维护在 skill_registry 单例中；安装/删除会同步操作本地文件系统
#   （下载技能包 / 删除已安装目录），查询类接口则直接读取 skill_registry 内存状态
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.orchestration.package_resolver import PackageResolver, PackageSpecifier
from app.orchestration.skill_registry import SkillSource, skill_registry
from app.orchestration.skill_sorting import sort_skills

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/skills", tags=["skills"])


class InstallSkillRequest(BaseModel):
    """安装技能请求体：specifier 为技能包说明符"""
    specifier: str


class SkillListResponse(BaseModel):
    """技能分页列表响应结构：items 为当前页数据，total/offset/limit/has_more 用于分页"""
    items: list[dict]
    total: int
    offset: int
    limit: int
    has_more: bool


@router.get("/", response_model=SkillListResponse)
async def list_skills(
    offset: int = Query(default=0, ge=0, description="偏移量"),
    limit: int = Query(default=24, ge=1, le=100, description="每页大小"),
    category: Optional[str] = None,
    plugin_name: Optional[str] = None,
    search: Optional[str] = None,
):
    """
    GET /api/skills/：分页查询技能列表，支持按分类/所属插件/关键字筛选。
    入参：offset —— 偏移量；limit —— 每页大小；category —— 按分类筛选；
      plugin_name —— 按所属插件筛选（"independent" 表示筛选无插件的独立技能）；
      search —— 按名称/描述关键字模糊搜索
    逻辑：取全部技能 -> 依次按分类/插件/关键字过滤 -> 排序 -> 按 offset/limit 截取分页 -> 序列化
    出参：SkillListResponse，包含当前页 items 及分页信息
    """
    # 1. 获取所有技能
    all_skills = skill_registry.list_skills()

    # 2. 筛选
    filtered = all_skills

    # 分类筛选
    if category:
        filtered = [s for s in filtered if s.category == category]

    # 插件筛选
    if plugin_name:
        if plugin_name == "independent":
            filtered = [s for s in filtered if not s.plugin_name]
        else:
            filtered = [s for s in filtered if s.plugin_name == plugin_name]

    # 搜索筛选
    if search:
        q = search.lower()
        filtered = [
            s for s in filtered
            if q in s.name.lower() or q in s.description.lower()
        ]

    # 3. 排序
    sorted_skills = sort_skills(filtered)

    # 4. 分页
    total = len(sorted_skills)
    paginated = sorted_skills[offset:offset+limit]

    # 5. 序列化并返回
    return {
        "items": [
            {
                "name": s.name,
                "description": s.description,
                "category": s.category,
                "required_skills": s.required_skills,
                "enabled": s.enabled,
                "source": s.source,
                "source_type": s.source_type.value if s.source_type else "",
                "install_path": s.install_path,
                "plugin_name": s.plugin_name,
                "version": s.version,
            }
            for s in paginated
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + limit < total,
    }


@router.get("/categories")
async def list_categories():
    """
    GET /api/skills/categories：按分类分组查询所有技能。
    入参：无
    逻辑：遍历所有技能，按 category 字段分组（无分类归入 "uncategorized"）
    出参：dict，键为分类名，值为该分类下技能列表（每项含 name/description/enabled）
    """
    result: dict[str, list[dict]] = {}
    for skill in skill_registry.list_skills():
        cat = skill.category or "uncategorized"
        result.setdefault(cat, []).append({
            "name": skill.name,
            "description": skill.description,
            "enabled": skill.enabled,
        })
    return result


@router.post("/refresh")
async def refresh_skills():
    """
    POST /api/skills/refresh：触发技能全量重新扫描。
    入参：无
    逻辑：调用 skill_registry.refresh() 重新扫描所有技能来源并刷新内存注册表
    出参：dict，{"total_skills": 刷新后的技能总数}
    """
    count = skill_registry.refresh()
    return {"total_skills": count}


@router.post("/install")
async def install_skill(req: InstallSkillRequest):
    """
    POST /api/skills/install：安装一个独立技能包（非插件形式）。
    入参：req.specifier —— 技能包说明符，不支持 PyPI
    逻辑：解析说明符 -> 在技能安装目录下创建对应子目录 -> 用 resolver 下载解析包 ->
      取包内技能目录（若包本身未声明则以安装路径本身兜底）逐个递归扫描注册为 GLOBAL 来源的技能；
      若一个技能都没扫描到（缺少 SKILL.md）则报错
    出参：dict，{"specifier":..., "installed_skills": 已安装技能数量, "install_path":...}
    """
    try:
        spec = PackageSpecifier.parse(req.specifier)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    if spec.spec_type == "pypi":
        raise HTTPException(status_code=400, detail="PyPI packages not yet supported")

    from app.config.settings import config_manager
    skill_install_dir = Path(config_manager.settings.skill.install_dir)
    target_dir = skill_install_dir / spec.name
    target_dir.mkdir(parents=True, exist_ok=True)

    resolver = PackageResolver(skill_install_dir)
    try:
        package = resolver.resolve(spec)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from None

    count = 0
    skill_dirs = package.skill_dirs
    if not skill_dirs:
        skill_dirs = [str(package.install_path)]

    for d in skill_dirs:
        count += skill_registry.scan_recursive(d, source_type=SkillSource.GLOBAL, plugin_name="")

    if count == 0:
        raise HTTPException(status_code=400, detail=f"未在 {req.specifier} 中发现技能（缺少 SKILL.md）")

    return {"specifier": req.specifier, "installed_skills": count, "install_path": str(target_dir)}


@router.delete("/{skill_name}")
async def delete_skill(skill_name: str):
    """
    DELETE /api/skills/{skill_name}：删除指定技能。
    入参：skill_name —— 技能名
    逻辑：从 skill_registry 注销该技能；若技能来源为 GLOBAL（独立安装），
      进一步在技能安装目录下定位其所属子目录并整个删除（rmtree）
    出参：dict，{"name": 技能名, "deleted": True}；技能不存在则 404
    """
    skill = skill_registry.get_skill(skill_name)
    if skill is None:
        raise HTTPException(status_code=404, detail="技能不存在")

    install_path = skill.install_path
    source_type = skill.source_type

    skill_registry.unregister_skill(skill_name)

    if source_type == SkillSource.GLOBAL and install_path:
        from app.config.settings import config_manager
        skill_install_dir = Path(config_manager.settings.skill.install_dir)
        for child in skill_install_dir.iterdir():
            if child.is_dir() and install_path.startswith(str(child)):
                import shutil
                shutil.rmtree(child, ignore_errors=True)
                break

    return {"name": skill_name, "deleted": True}


@router.get("/{skill_name}")
async def get_skill_detail(skill_name: str):
    """
    GET /api/skills/{skill_name}：查询技能详情，含 SKILL.md 正文内容。
    入参：skill_name —— 技能名
    逻辑：从 skill_registry 取技能元信息，再取其内容文件（不存在则返回空字符串）
    出参：dict，包含 name/description/category/required_skills/enabled/source/source_type/
      install_path/plugin_name/version/content；技能不存在则 404
    """
    skill = skill_registry.get_skill(skill_name)
    if skill is None:
        raise HTTPException(status_code=404, detail="技能不存在")

    content = skill_registry.get_skill_content(skill_name)
    return {
        "name": skill.name,
        "description": skill.description,
        "category": skill.category,
        "required_skills": skill.required_skills,
        "enabled": skill.enabled,
        "source": skill.source,
        "source_type": skill.source_type.value if skill.source_type else "",
        "install_path": skill.install_path,
        "plugin_name": skill.plugin_name,
        "version": skill.version,
        "content": content or "",
    }


@router.post("/{skill_name}/enable")
async def enable_skill(skill_name: str):
    """
    POST /api/skills/{skill_name}/enable：启用指定技能。
    入参：skill_name —— 技能名
    出参：dict，{"name": 技能名, "enabled": True}；技能不存在则 404
    """
    ok = skill_registry.enable_skill(skill_name)
    if not ok:
        raise HTTPException(status_code=404, detail="技能不存在")
    return {"name": skill_name, "enabled": True}


@router.post("/{skill_name}/disable")
async def disable_skill(skill_name: str):
    """
    POST /api/skills/{skill_name}/disable：禁用指定技能。
    入参：skill_name —— 技能名
    出参：dict，{"name": 技能名, "enabled": False}；技能不存在则 404
    """
    ok = skill_registry.disable_skill(skill_name)
    if not ok:
        raise HTTPException(status_code=404, detail="技能不存在")
    return {"name": skill_name, "enabled": False}
