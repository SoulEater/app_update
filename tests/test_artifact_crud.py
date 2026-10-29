"""产物批量删除回归，使用真实 CRUDPlus 与临时 SQLite，不访问宿主数据库。"""

from pathlib import Path

import pytest

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from backend.plugin.app_update.crud.crud_artifact import artifact_dao
from backend.plugin.app_update.model import Artifact


@pytest.mark.anyio
async def test_delete_all_artifacts_only_for_requested_release(tmp_path: Path) -> None:
    engine = create_async_engine(f'sqlite+aiosqlite:///{tmp_path / "artifacts.sqlite"}')
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Artifact.__table__.create)
        async with AsyncSession(engine, expire_on_commit=False) as session, session.begin():
            for index, (release_id, kind) in enumerate(
                [(10, 'installer'), (10, 'blockmap'), (10, 'manifest'), (11, 'installer')], start=1
            ):
                artifact = Artifact(
                    release_id=release_id,
                    kind=kind,
                    filename=f'{kind}.bin',
                    storage_path=f'{release_id}/{kind}.bin',
                    size=1,
                    sha256='a' * 64,
                )
                artifact.id = index
                session.add(artifact)
            await session.flush()
            assert await artifact_dao.delete_by_release(session, 10) == 3
            assert await session.scalar(select(func.count()).select_from(Artifact)) == 1
            assert await session.scalar(select(Artifact.release_id)) == 11
            assert await artifact_dao.delete_by_release(session, 10) == 0
    finally:
        await engine.dispose()
