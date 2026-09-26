"""FastAPI 接口层。

单刃调用：
- POST /v1/diffraction/parameters  返回 v、余隙、第一菲涅尔区半径
- POST /v1/diffraction/assessment  同样输入，追加附加损耗与通视判定
- POST /v1/diffraction/batch       一批链路一次算完，各条独立
多刃（地形剖面）调用：
- POST /v1/diffraction/profile/assessment  整条剖面的级联绕射评估
- POST /v1/diffraction/profile/batch       一组剖面一次算完，各条独立
另加：
- GET  /v1/examples/ridge          预置的山脊略微遮挡算例（损耗 > 6 dB）
- GET  /healthz                    存活探针
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .batch import BatchItem, evaluate_batch
from .presets import RIDGE_PRESET
from .profile_batch import ProfileBatchItem, evaluate_profile_batch
from .profile_service import ProfileAssessment, assess_profile
from .schemas import (
    BatchItemResponse,
    BatchRequest,
    BatchResponse,
    ErrorBody,
    ErrorResponse,
    FullAssessmentResponse,
    LinkInput,
    ObstacleContribution,
    ParameterAssessmentResponse,
    ProfileAssessmentRequest,
    ProfileAssessmentResponse,
    ProfileBatchItemResponse,
    ProfileBatchRequest,
    ProfileBatchResponse,
)
from .service import FullAssessment, ParameterAssessment, assess_full, assess_parameters
from .validation import ValidationError

app = FastAPI(
    title="Knife-Edge Diffraction Service",
    version="1.0.0",
    description="单刃障碍绕射内核：菲涅尔参数、余隙、第一菲涅尔区半径与附加损耗。",
)


@app.exception_handler(ValidationError)
async def validation_error_handler(_: Request, exc: ValidationError) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code="INVALID_INPUT", reason=exc.reason))
    return JSONResponse(status_code=400, content=body.model_dump())


def _to_parameter_response(
    link_id: str | None, a: ParameterAssessment
) -> ParameterAssessmentResponse:
    return ParameterAssessmentResponse(
        link_id=link_id,
        v=a.v,
        clearance_m=a.clearance_m,
        clearance_fresnel_ratio=a.clearance_fresnel_ratio,
        first_fresnel_radius_m=a.first_fresnel_radius_m,
        wavelength_m=a.wavelength_m,
    )


def _to_full_response(link_id: str | None, a: FullAssessment) -> FullAssessmentResponse:
    return FullAssessmentResponse(
        link_id=link_id,
        v=a.v,
        clearance_m=a.clearance_m,
        clearance_fresnel_ratio=a.clearance_fresnel_ratio,
        first_fresnel_radius_m=a.first_fresnel_radius_m,
        wavelength_m=a.wavelength_m,
        loss_db=a.loss_db,
        is_los=a.is_los,
    )


def _to_profile_response(
    profile_id: str | None, a: ProfileAssessment
) -> ProfileAssessmentResponse:
    return ProfileAssessmentResponse(
        profile_id=profile_id,
        path_length_m=a.path_length_m,
        frequency_mhz=a.frequency_mhz,
        wavelength_m=a.wavelength_m,
        total_loss_db=a.total_loss_db,
        is_los=a.is_los,
        obstacle_count=len(a.obstacles),
        obstacles=[
            ObstacleContribution(
                sample_index=o.sample_index,
                distance_m=o.distance_m,
                depth=o.depth,
                d1_m=o.d1_m,
                d2_m=o.d2_m,
                h_m=o.h_m,
                v=o.v,
                loss_db=o.loss_db,
            )
            for o in a.obstacles
        ],
    )


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.post(
    "/v1/diffraction/parameters",
    response_model=ParameterAssessmentResponse,
    responses={400: {"model": ErrorResponse}},
)
def diffraction_parameters(link: LinkInput) -> ParameterAssessmentResponse:
    """第一类调用：返回 v、余隙与第一菲涅尔区半径。"""
    a = assess_parameters(link.d1_m, link.d2_m, link.h_m, link.frequency_mhz)
    return _to_parameter_response(link.link_id, a)


@app.post(
    "/v1/diffraction/assessment",
    response_model=FullAssessmentResponse,
    responses={400: {"model": ErrorResponse}},
)
def diffraction_assessment(link: LinkInput) -> FullAssessmentResponse:
    """第二类调用：追加附加损耗与是否通视的判定。"""
    a = assess_full(link.d1_m, link.d2_m, link.h_m, link.frequency_mhz)
    return _to_full_response(link.link_id, a)


@app.post(
    "/v1/diffraction/batch",
    response_model=BatchResponse,
    responses={400: {"model": ErrorResponse}},
)
def diffraction_batch(request: BatchRequest) -> BatchResponse:
    """批量调用：各条链路独立评估，单条失败不影响其他。"""
    items = [
        BatchItem(
            link_id=link.link_id,
            d1_m=link.d1_m,
            d2_m=link.d2_m,
            h_m=link.h_m,
            frequency_mhz=link.frequency_mhz,
        )
        for link in request.links
    ]
    results = evaluate_batch(items)
    return BatchResponse(
        count=len(results),
        results=[
            BatchItemResponse(
                link_id=r.link_id,
                ok=r.ok,
                result=_to_full_response(r.link_id, r.result) if r.ok else None,
                error=None
                if r.ok
                else ErrorBody(code="INVALID_INPUT", reason=r.error_reason or ""),
            )
            for r in results
        ],
    )


@app.get(
    "/v1/examples/ridge",
    response_model=FullAssessmentResponse,
)
def ridge_example() -> FullAssessmentResponse:
    """预置算例：山脊略微遮挡，附加损耗大于 6 dB。"""
    p = RIDGE_PRESET
    a = assess_full(p.d1_m, p.d2_m, p.h_m, p.frequency_mhz)
    return _to_full_response(p.link_id, a)


def _profile_points(request: ProfileAssessmentRequest) -> list[tuple[float, float]]:
    return [(p.distance_m, p.elevation_m) for p in request.points]


@app.post(
    "/v1/diffraction/profile/assessment",
    response_model=ProfileAssessmentResponse,
    responses={400: {"model": ErrorResponse}},
)
def profile_assessment(request: ProfileAssessmentRequest) -> ProfileAssessmentResponse:
    """多刃调用：吃整条地形剖面，自己摊出参与绕射的障碍并级联合成。"""
    a = assess_profile(
        request.path_length_m,
        request.tx_antenna_height_m,
        request.tx_site_elevation_m,
        request.rx_antenna_height_m,
        request.rx_site_elevation_m,
        request.frequency_mhz,
        _profile_points(request),
    )
    return _to_profile_response(request.profile_id, a)


@app.post(
    "/v1/diffraction/profile/batch",
    response_model=ProfileBatchResponse,
    responses={400: {"model": ErrorResponse}},
)
def profile_batch(request: ProfileBatchRequest) -> ProfileBatchResponse:
    """多刃批量调用：各条剖面独立评估，单条失败不影响其他。"""
    items = [
        ProfileBatchItem(
            profile_id=p.profile_id,
            path_length_m=p.path_length_m,
            tx_antenna_height_m=p.tx_antenna_height_m,
            tx_site_elevation_m=p.tx_site_elevation_m,
            rx_antenna_height_m=p.rx_antenna_height_m,
            rx_site_elevation_m=p.rx_site_elevation_m,
            frequency_mhz=p.frequency_mhz,
            points=tuple(_profile_points(p)),
        )
        for p in request.profiles
    ]
    results = evaluate_profile_batch(items)
    return ProfileBatchResponse(
        count=len(results),
        results=[
            ProfileBatchItemResponse(
                profile_id=r.profile_id,
                ok=r.ok,
                result=_to_profile_response(r.profile_id, r.result) if r.ok else None,
                error=None
                if r.ok
                else ErrorBody(code="INVALID_INPUT", reason=r.error_reason or ""),
            )
            for r in results
        ],
    )
