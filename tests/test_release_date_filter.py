"""版本发布时间筛选测试。"""

from datetime import date, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.common.exception import errors
from backend.plugin.app_update.api.v1 import release as release_api
from backend.plugin.app_update.crud.crud_release import release_dao
from backend.plugin.app_update.service import release_service as rs
from backend.utils.timezone import timezone


async def test_release_api_forwards_published_date_range() -> None:
    db = MagicMock()
    published_start = date(2026, 8, 1)
    published_end = date(2026, 8, 26)
    with patch.object(
        release_api.release_service,
        'get_list',
        new_callable=AsyncMock,
        return_value={'items': [], 'total': 0},
    ) as get_list:
        response = await release_api.get_releases_paginated(
            db=db,
            application_id=1,
            channel_id=2,
            status='published',
            version='0.1',
            published_start=published_start,
            published_end=published_end,
        )

    assert response.data == {'items': [], 'total': 0}
    get_list.assert_awaited_once_with(
        db=db,
        application_id=1,
        channel_id=2,
        status='published',
        version='0.1',
        published_start=published_start,
        published_end=published_end,
    )


async def _get_service_filter_kwargs(
    *,
    published_start: date | None = None,
    published_end: date | None = None,
) -> dict[str, Any]:
    db = MagicMock()
    with (
        patch.object(rs, 'release_dao') as mocked_release_dao,
        patch.object(rs, 'artifact_dao') as mocked_artifact_dao,
        patch.object(rs, 'paging_data', new_callable=AsyncMock) as mocked_paging_data,
    ):
        mocked_release_dao.get_detail_select = AsyncMock(return_value=MagicMock())
        mocked_artifact_dao.get_by_release_ids = AsyncMock(return_value=[])
        mocked_paging_data.return_value = {'items': [], 'total': 0}

        await rs.release_service.get_list(
            db=db,
            published_start=published_start,
            published_end=published_end,
        )

        return mocked_release_dao.get_detail_select.await_args.kwargs


async def test_release_service_supports_published_start_only() -> None:
    kwargs = await _get_service_filter_kwargs(published_start=date(2026, 8, 1))

    assert kwargs['published_start_at'] == datetime(2026, 8, 1, tzinfo=timezone.tz_info)
    assert kwargs['published_end_before'] is None


async def test_release_service_supports_published_end_only_and_includes_end_day() -> None:
    kwargs = await _get_service_filter_kwargs(published_end=date(2026, 8, 26))

    assert kwargs['published_start_at'] is None
    assert kwargs['published_end_before'] == datetime(2026, 8, 27, tzinfo=timezone.tz_info)


async def test_release_service_builds_complete_range_in_configured_timezone() -> None:
    kwargs = await _get_service_filter_kwargs(
        published_start=date(2026, 8, 1),
        published_end=date(2026, 8, 26),
    )

    assert kwargs['published_start_at'] == datetime(2026, 8, 1, tzinfo=timezone.tz_info)
    assert kwargs['published_end_before'] == datetime(2026, 8, 27, tzinfo=timezone.tz_info)
    assert kwargs['published_start_at'].utcoffset() == timezone.tz_info.utcoffset(kwargs['published_start_at'])


async def test_release_service_rejects_reversed_published_range() -> None:
    with pytest.raises(errors.RequestError, match='开始日期不能晚于结束日期'):
        await rs.release_service.get_list(
            db=MagicMock(),
            published_start=date(2026, 8, 27),
            published_end=date(2026, 8, 26),
        )


async def test_release_crud_uses_inclusive_start_and_exclusive_end() -> None:
    published_start_at = datetime(2026, 8, 1, tzinfo=timezone.tz_info)
    published_end_before = datetime(2026, 8, 27, tzinfo=timezone.tz_info)

    statement = await release_dao.get_detail_select(
        published_start_at=published_start_at,
        published_end_before=published_end_before,
    )
    compiled = statement.compile()
    sql = str(compiled)
    params = tuple(compiled.params.values())

    assert 'app_update_release.published_at >=' in sql
    assert 'app_update_release.published_at <' in sql
    assert published_start_at in params
    assert published_end_before in params
    assert 'published_at IS NULL' not in sql
