"""更新渠道模型"""

import sqlalchemy as sa

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import UniqueConstraint

from backend.common.model import Base, id_key
from backend.plugin.app_update.enums import ChannelStatus


class Channel(Base):
    """应用更新-渠道表"""

    __tablename__ = 'app_update_channel'
    __table_args__ = (
        UniqueConstraint('application_id', 'code', name='uk_app_update_channel_app_code'),
        {'comment': '应用更新-渠道表'},
    )

    id: Mapped[id_key] = mapped_column(init=False)
    application_id: Mapped[int] = mapped_column(sa.BigInteger, index=True, comment='所属应用ID')
    code: Mapped[str] = mapped_column(sa.String(32), comment='渠道编码')
    name: Mapped[str] = mapped_column(sa.String(64), comment='渠道名称')
    status: Mapped[str] = mapped_column(
        sa.String(16),
        default=ChannelStatus.enabled.value,
        comment='状态: enabled/disabled',
    )
    current_release_id: Mapped[int | None] = mapped_column(
        sa.BigInteger,
        default=None,
        index=True,
        comment='客户端当前可见版本ID，逻辑关联 app_update_release.id',
    )
