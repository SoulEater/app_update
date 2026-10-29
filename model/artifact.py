"""版本产物模型"""

import sqlalchemy as sa

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import UniqueConstraint

from backend.common.model import Base, id_key


class Artifact(Base):
    """应用更新-产物表"""

    __tablename__ = 'app_update_artifact'
    __table_args__ = (
        UniqueConstraint('release_id', 'kind', name='uk_app_update_artifact_release_kind'),
        {'comment': '应用更新-产物表'},
    )

    id: Mapped[id_key] = mapped_column(init=False)
    release_id: Mapped[int] = mapped_column(sa.BigInteger, index=True, comment='所属版本ID')
    kind: Mapped[str] = mapped_column(sa.String(16), comment='产物类型: installer/blockmap/manifest')
    filename: Mapped[str] = mapped_column(sa.String(255), comment='安全文件名')
    storage_path: Mapped[str] = mapped_column(sa.String(512), comment='相对存储根目录路径')
    size: Mapped[int] = mapped_column(sa.BigInteger, comment='字节数')
    sha256: Mapped[str] = mapped_column(sa.String(64), comment='小写十六进制 SHA-256')
    sha512: Mapped[str | None] = mapped_column(sa.String(128), default=None, comment='Base64 SHA-512，安装包必填')
