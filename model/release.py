"""发布版本模型"""

from datetime import datetime

import sqlalchemy as sa

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import UniqueConstraint

from backend.common.model import Base, TimeZone, id_key
from backend.plugin.app_update.enums import ReleaseStatus


class Release(Base):
    """应用更新-版本表"""

    __tablename__ = 'app_update_release'
    __table_args__ = (
        UniqueConstraint(
            'application_id',
            'channel_id',
            'version',
            'platform',
            'arch',
            name='uk_app_update_release_identity',
        ),
        {'comment': '应用更新-版本表'},
    )

    id: Mapped[id_key] = mapped_column(init=False)
    application_id: Mapped[int] = mapped_column(sa.BigInteger, index=True, comment='所属应用ID')
    channel_id: Mapped[int] = mapped_column(sa.BigInteger, index=True, comment='所属渠道ID')
    version: Mapped[str] = mapped_column(sa.String(32), comment='版本号，严格 x.y.z')
    platform: Mapped[str] = mapped_column(sa.String(16), default='win32', comment='平台')
    arch: Mapped[str] = mapped_column(sa.String(16), default='x64', comment='架构')
    release_notes: Mapped[str | None] = mapped_column(sa.Text, default=None, comment='更新说明')
    status: Mapped[str] = mapped_column(
        sa.String(16),
        default=ReleaseStatus.draft.value,
        comment='状态: draft/published/paused',
    )
    signature_status: Mapped[str | None] = mapped_column(
        sa.String(32),
        default=None,
        comment='来自 release manifest 的签名状态，仅展示',
    )
    published_by: Mapped[int | None] = mapped_column(
        sa.BigInteger,
        default=None,
        index=True,
        comment='发布人 sys_user.id，逻辑关联',
    )
    published_at: Mapped[datetime | None] = mapped_column(TimeZone, default=None, comment='发布时间')
