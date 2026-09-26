"""多刃剖面接口数据模型（Pydantic）。

与单刃接口的 schemas.py 分开存放：多刃是新增的一层，不改动旧模型。
距离单位 m，频率 MHz，海拔/高度单位 m；超出高度（遮挡为正）由
服务依据两端天线顶连线自行折算，调用方不得也不需要预先折算。
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .schemas import ErrorBody


class StationInput(BaseModel):
    """链路一端：所在地地面海拔与天线架设高度。"""

    model_config = ConfigDict(extra="forbid")

    ground_elevation_m: float = Field(description="该端所在地地面海拔，m")
    antenna_height_m: float = Field(
        description="天线相对地面的架设高度，m（非负，由语义校验拒绝负值）"
    )


class ProfileSampleInput(BaseModel):
    """地形剖面上的一个采样点：到发射端里程 + 该点地面海拔。"""

    model_config = ConfigDict(extra="forbid")

    distance_m: float = Field(
        description="采样点到发射端的水平里程，m；严格递增且位于收发之间"
    )
    elevation_m: float = Field(description="采样点地面海拔，m")


class ProfileLinkInput(BaseModel):
    """整条地形剖面链路输入。"""

    model_config = ConfigDict(extra="forbid")

    link_id: Optional[str] = None
    frequency_mhz: float = Field(description="频率，MHz（必须为正）")
    path_length_m: float = Field(
        description="收发两端之间的水平总距离，m（必须为正）"
    )
    tx: StationInput = Field(description="发射端地面海拔与天线架设高度")
    rx: StationInput = Field(description="接收端地面海拔与天线架设高度")
    # 允许空剖面：全程通视。采样点之间不做地形插值。
    profile: list[ProfileSampleInput] = Field(default_factory=list)


class ObstacleSegmentResponse(BaseModel):
    """障碍被选出时所在子链路的几何。"""

    left_distance_m: float
    right_distance_m: float
    d1_m: float = Field(description="障碍到该子链路左端的水平距离，m")
    d2_m: float = Field(description="障碍到该子链路右端的水平距离，m")
    h_m: float = Field(
        description="障碍山顶相对该子链路参考线的超出高度，m；遮挡为正"
    )


class ObstacleContributionResponse(BaseModel):
    """一个被选中参与合成的刃形障碍及其那份附加损耗。"""

    sample_index: int = Field(description="对应输入剖面中的采样点序号（0 起）")
    distance_m: float = Field(description="到发射端的水平里程，m")
    ground_elevation_m: float
    side: str = Field(
        description="所在侧：root=全链路主障碍，tx_side=主障碍发射端一侧，rx_side=接收端一侧"
    )
    depth: int = Field(description="递归深度：0 为全链路主障碍")
    segment: ObstacleSegmentResponse
    v: float = Field(description="相对所在子链路参考线的菲涅尔参数")
    loss_db: float = Field(description="该障碍这一份单刃附加损耗，dB")


class ProfileAssessmentResponse(BaseModel):
    """整条剖面的多刃评估结果。"""

    link_id: Optional[str] = None
    total_loss_db: float
    is_los: bool
    obstacle_count: int
    obstacles: list[ObstacleContributionResponse]
    wavelength_m: float
    path_length_m: float


class ProfileBatchItemResponse(BaseModel):
    link_id: Optional[str]
    ok: bool
    result: Optional[ProfileAssessmentResponse] = None
    error: Optional[ErrorBody] = None


class ProfileBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    links: list[ProfileLinkInput] = Field(min_length=1, max_length=1000)


class ProfileBatchResponse(BaseModel):
    count: int
    results: list[ProfileBatchItemResponse]
