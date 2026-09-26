"""多刃剖面的批量调度：一组剖面一次算完。

每条剖面独立评估、互不覆盖：单条输入不合法只在该条的结果里
携带错误，不影响同批其他剖面。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Optional, Tuple

from .profile_service import ProfileAssessment, assess_profile
from .validation import ValidationError


@dataclass(frozen=True)
class ProfileBatchItem:
    """批量请求中的一条地形剖面。"""

    profile_id: Optional[str]
    path_length_m: float
    tx_antenna_height_m: float
    tx_site_elevation_m: float
    rx_antenna_height_m: float
    rx_site_elevation_m: float
    frequency_mhz: float
    points: Tuple[Tuple[float, float], ...]  # (里程, 海拔) 序列


@dataclass(frozen=True)
class ProfileBatchItemResult:
    """单条剖面的评估结果：成功带 result，失败带 error_reason。"""

    profile_id: Optional[str]
    ok: bool
    result: Optional[ProfileAssessment] = None
    error_reason: Optional[str] = None


def evaluate_profile_batch(
    items: Iterable[ProfileBatchItem],
    assess: Callable[..., ProfileAssessment] = assess_profile,
) -> list[ProfileBatchItemResult]:
    """逐条调度评估，结果与输入一一对应、顺序保持一致。"""
    results: list[ProfileBatchItemResult] = []
    for item in items:
        try:
            assessment = assess(
                item.path_length_m,
                item.tx_antenna_height_m,
                item.tx_site_elevation_m,
                item.rx_antenna_height_m,
                item.rx_site_elevation_m,
                item.frequency_mhz,
                item.points,
            )
        except ValidationError as exc:
            results.append(
                ProfileBatchItemResult(
                    profile_id=item.profile_id, ok=False, error_reason=exc.reason
                )
            )
        else:
            results.append(
                ProfileBatchItemResult(
                    profile_id=item.profile_id, ok=True, result=assessment
                )
            )
    return results
