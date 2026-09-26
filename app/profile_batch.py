"""多刃剖面批量调度：多条剖面成组评估，逐条独立、错误隔离。

与 app.batch（单刃批量）同样的口径：每条剖面独立校验与评估，
单条剖面校验失败只在它自己的结果里携带带原因的错误，不影响
同批其他剖面，结果顺序与输入一一对应、互不覆盖。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from .profile_service import ProfileAssessment, assess_profile
from .validation import ValidationError


@dataclass(frozen=True)
class ProfileBatchItem:
    """批量请求中的一条地形剖面链路。"""

    link_id: Optional[str]
    frequency_mhz: float
    path_length_m: float
    tx_ground_elevation_m: float
    tx_antenna_height_m: float
    rx_ground_elevation_m: float
    rx_antenna_height_m: float
    profile_samples: Sequence[tuple[float, float]]


@dataclass(frozen=True)
class ProfileBatchItemResult:
    """单条剖面的评估结果：成功带 result，失败带 error_reason。"""

    link_id: Optional[str]
    ok: bool
    result: Optional[ProfileAssessment] = None
    error_reason: Optional[str] = None


def evaluate_profile_batch(
    items: Iterable[ProfileBatchItem],
) -> list[ProfileBatchItemResult]:
    """逐条调度剖面评估，结果与输入一一对应、顺序保持一致。"""
    results: list[ProfileBatchItemResult] = []
    for item in items:
        try:
            assessment = assess_profile(
                frequency_mhz=item.frequency_mhz,
                path_length_m=item.path_length_m,
                tx_ground_elevation_m=item.tx_ground_elevation_m,
                tx_antenna_height_m=item.tx_antenna_height_m,
                rx_ground_elevation_m=item.rx_ground_elevation_m,
                rx_antenna_height_m=item.rx_antenna_height_m,
                profile_samples=item.profile_samples,
            )
        except ValidationError as exc:
            results.append(
                ProfileBatchItemResult(
                    link_id=item.link_id, ok=False, error_reason=exc.reason
                )
            )
        else:
            results.append(
                ProfileBatchItemResult(
                    link_id=item.link_id, ok=True, result=assessment
                )
            )
    return results
