"""接口数据模型（Pydantic）。"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class LinkInput(BaseModel):
    """单条链路输入。距离 m，频率 MHz，h 遮挡为正。"""

    model_config = ConfigDict(extra="forbid")

    link_id: Optional[str] = None
    d1_m: float = Field(description="障碍到发射端的水平距离，m")
    d2_m: float = Field(description="障碍到接收端的水平距离，m")
    h_m: float = Field(description="障碍相对直视线的超出高度，m；遮挡为正")
    frequency_mhz: float = Field(description="频率，MHz")


class BatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    links: list[LinkInput] = Field(min_length=1, max_length=1000)


class ParameterAssessmentResponse(BaseModel):
    link_id: Optional[str]
    v: float
    clearance_m: float
    clearance_fresnel_ratio: float
    first_fresnel_radius_m: float
    wavelength_m: float


class FullAssessmentResponse(ParameterAssessmentResponse):
    loss_db: float
    is_los: bool


class ErrorBody(BaseModel):
    code: str
    reason: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class BatchItemResponse(BaseModel):
    link_id: Optional[str]
    ok: bool
    result: Optional[FullAssessmentResponse] = None
    error: Optional[ErrorBody] = None


class BatchResponse(BaseModel):
    count: int
    results: list[BatchItemResponse]


class ProfilePointInput(BaseModel):
    """地形剖面采样点：里程 + 地面海拔。"""

    model_config = ConfigDict(extra="forbid")

    distance_m: float = Field(description="采样点到发射端的水平距离，m")
    elevation_m: float = Field(description="采样点地面海拔，m")


class ProfileAssessmentRequest(BaseModel):
    """多刃剖面评估输入：整条地形剖面 + 两端天线参数 + 频率。"""

    model_config = ConfigDict(extra="forbid")

    profile_id: Optional[str] = None
    path_length_m: float = Field(description="收发间水平总距离，m")
    tx_antenna_height_m: float = Field(description="发射端天线架设高度，m，不为负")
    tx_site_elevation_m: float = Field(description="发射端所在地海拔，m")
    rx_antenna_height_m: float = Field(description="接收端天线架设高度，m，不为负")
    rx_site_elevation_m: float = Field(description="接收端所在地海拔，m")
    frequency_mhz: float = Field(description="频率，MHz")
    points: list[ProfilePointInput] = Field(
        max_length=10000, description="按里程排列的地形剖面采样点"
    )


class ObstacleContribution(BaseModel):
    """被摊出并参与合成的一处障碍。"""

    sample_index: int = Field(description="对应剖面 points 的下标")
    distance_m: float = Field(description="里程（到发射端的水平距离），m")
    depth: int = Field(description="选取层深：0 为全链路主障碍")
    d1_m: float = Field(description="子链路内到左端点的水平距离，m")
    d2_m: float = Field(description="子链路内到右端点的水平距离，m")
    h_m: float = Field(description="相对子链路参考直视线的超出高度，m")
    v: float = Field(description="相对所在子链路参考线的菲涅尔参数")
    loss_db: float = Field(description="这一处障碍贡献的附加损耗，dB")


class ProfileAssessmentResponse(BaseModel):
    profile_id: Optional[str]
    path_length_m: float
    frequency_mhz: float
    wavelength_m: float
    total_loss_db: float
    is_los: bool
    obstacle_count: int
    obstacles: list[ObstacleContribution]


class ProfileBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profiles: list[ProfileAssessmentRequest] = Field(min_length=1, max_length=1000)


class ProfileBatchItemResponse(BaseModel):
    profile_id: Optional[str]
    ok: bool
    result: Optional[ProfileAssessmentResponse] = None
    error: Optional[ErrorBody] = None


class ProfileBatchResponse(BaseModel):
    count: int
    results: list[ProfileBatchItemResponse]
