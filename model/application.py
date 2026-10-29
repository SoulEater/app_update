"""应用模型"""

import sqlalchemy as sa

from sqlalchemy.orm import Mapped, mapped_column

from backend.common.model import Base, id_key
from backend.plugin.app_update.enums import ApplicationStatus


class Application(Base):
    """应用更新-应用表"""

    __tablename__ = 'app_update_application'

    id: Mapped[id_key] = mapped_column(init=False)
    key: Mapped[str] = mapped_column(sa.String(64), unique=True, index=True, comment='应用标识')
    name: Mapped[str] = mapped_column(sa.String(128), comment='应用名称')
    description: Mapped[str | None] = mapped_column(sa.Text, default=None, comment='应用说明')
    status: Mapped[str] = mapped_column(
        sa.String(16),
        default=ApplicationStatus.enabled.value,
        comment='状态: enabled/disabled',
    )
