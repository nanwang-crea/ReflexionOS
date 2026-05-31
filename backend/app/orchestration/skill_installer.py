import logging
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from git import Repo
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class InstallResult(BaseModel):
    success: bool
    install_path: str = ""
    error: str = ""


class SkillInstaller:
    def __init__(self, install_dir: Path | str):
        self.install_dir = Path(install_dir)
        self.install_dir.mkdir(parents=True, exist_ok=True)

    def install(
        self,
        url: str,
        skill_name: str,
        subdir: str = "",
        branch: str = "main",
    ) -> InstallResult:
        target_dir = self.install_dir / skill_name
        if target_dir.exists():
            return InstallResult(
                success=False,
                error=f"Skill '{skill_name}' already exists at {target_dir}",
            )

        try:
            with TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                clone_dir = tmp_path / "repo"
                logger.info("Cloning %s (branch=%s)", url, branch)
                Repo.clone_from(url, str(clone_dir), branch=branch, depth=1)

                source_dir = clone_dir / subdir if subdir else clone_dir / skill_name
                if not source_dir.is_dir():
                    source_dir = clone_dir
                    if not (source_dir / "SKILL.md").exists():
                        return InstallResult(
                            success=False,
                            error=f"SKILL.md not found in repo at {subdir or skill_name}",
                        )

                skill_file = source_dir / "SKILL.md"
                if not skill_file.exists():
                    return InstallResult(
                        success=False,
                        error=f"SKILL.md not found at {source_dir}",
                    )

                shutil.copytree(str(source_dir), str(target_dir))
                logger.info("Installed skill '%s' to %s", skill_name, target_dir)

            return InstallResult(
                success=True,
                install_path=str(target_dir),
            )
        except Exception as exc:
            logger.exception("Failed to install skill '%s'", skill_name)
            return InstallResult(success=False, error=str(exc))

    def uninstall(self, skill_name: str) -> InstallResult:
        target_dir = self.install_dir / skill_name
        if not target_dir.exists():
            return InstallResult(
                success=False,
                error=f"Skill '{skill_name}' not found at {target_dir}",
            )

        try:
            shutil.rmtree(str(target_dir))
            logger.info("Uninstalled skill '%s'", skill_name)
            return InstallResult(success=True, install_path=str(target_dir))
        except Exception as exc:
            logger.exception("Failed to uninstall skill '%s'", skill_name)
            return InstallResult(success=False, error=str(exc))
