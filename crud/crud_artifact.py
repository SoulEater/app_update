"""版本产物 CRUD 操作"""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy_crud_plus import CRUDPlus

from backend.plugin.app_update.model import Artifact


class CRUDArtifact(CRUDPlus[Artifact]):
    """产物 CRUD 类"""

    async def get(self, db: AsyncSession, pk: int) -> Artifact | None:
        """获取产物"""
        return await self.select_model(db, pk)

    async def get_by_release(self, db: AsyncSession, release_id: int) -> Sequence[Artifact]:
        """获取版本全部产物"""
        return await self.select_models(db, release_id=release_id)

    async def get_by_release_kind(self, db: AsyncSession, release_id: int, kind: str) -> Artifact | None:
        """获取版本指定类型产物"""
        return await self.select_model_by_column(db, release_id=release_id, kind=kind)

    async def get_by_release_ids(self, db: AsyncSession, release_ids: Sequence[int]) -> Sequence[Artifact]:
        """批量获取多个版本的全部产物，避免列表接口产生 N+1 查询"""
        if not release_ids:
            return []
        stmt = select(Artifact).where(Artifact.release_id.in_(release_ids)).order_by(Artifact.release_id, Artifact.id)
        result = await db.execute(stmt)
        return result.scalars().all()

    async def replace_release_artifacts(self, db: AsyncSession, release_id: int, artifacts: list[Artifact]) -> None:
        """以给定产物集合替换版本产物"""
        for existing in await self.get_by_release(db, release_id):
            await db.delete(existing)
        await db.flush()
        for artifact in artifacts:
            db.add(artifact)
        await db.flush()

    async def delete_by_release(self, db: AsyncSession, release_id: int) -> int:
        """删除版本全部产物登记"""
        return await self.delete_model_by_column(db, allow_multiple=True, release_id=release_id)


artifact_dao: CRUDArtifact = CRUDArtifact(Artifact)
