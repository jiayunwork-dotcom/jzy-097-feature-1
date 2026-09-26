# 刃形绕射损耗计算服务

无线传播评估组内部使用的绕射内核，仅经 HTTP 提供。单刃能力根据链路几何与频率计算菲涅尔–基尔霍夫参数、余隙、第一菲涅尔区半径与附加损耗；多刃能力直接吃下沿链路的整条地形剖面，自行折算余隙、递归选取主障碍并级联合成总附加损耗。不做自由空间链路预算，与光学缝衍射无关。

## 定义与约定

- 几何：`d1_m`、`d2_m` 为障碍到发/收端的水平距离（m，必须为正）；`h_m` 为障碍相对收发直视线的超出高度（m），**遮挡为正、低于直视线为负**。
- 频率：`frequency_mhz`（MHz，必须为正），波长 λ = c / f。
- 菲涅尔参数：`v = h·√(2·(d1+d2) / (λ·d1·d2))`。
- 第一菲涅尔区半径（障碍截面）：`r1 = √(λ·d1·d2/(d1+d2))`；余隙 = −h。
- 附加损耗（ITU-R P.526 单刃近似，标准库手写）：
  - `v ≤ −0.78`：0 dB（余隙充足时不硬加损耗）；
  - `v > −0.78`：`6.9 + 20·log10(√((v−0.1)²+1) + v − 0.1)`。
  - 擦边 `v=0` 时约 6.0 dB；v 增大损耗单调升高。
- 通视判定：`v < 0`（障碍顶部低于直视线）为通视。

## 模块划分

| `app/geometry.py` | 链路几何与余隙 |
| `app/fresnel.py` | 菲涅尔–基尔霍夫参数 v、波长换算 |
| `app/zone.py` | 第一菲涅尔区半径 |
| `app/loss.py` | 附加损耗近似 |
| `app/validation.py` | 输入校验（带原因拒绝） |
| `app/service.py` | 单刃评估编排 |
| `app/batch.py` | 单刃批量调度（逐条独立、错误隔离） |
| `app/presets.py` | 预置算例（山脊略微遮挡，损耗 > 6 dB） |
| `app/schemas.py` | 单刃接口数据模型 |
| `app/profile.py` | 地形剖面表示、直视线余隙折算、剖面校验 |
| `app/multiedge.py` | 主障碍递归选取（Deygout 主障碍法）与分段 |
| `app/synthesis.py` | 多刃损耗的级联合成 |
| `app/profile_service.py` | 多刃剖面评估编排 |
| `app/profile_batch.py` | 多刃批量调度（逐条独立、错误隔离） |
| `app/profile_schemas.py` | 多刃接口数据模型 |
| `app/main.py` | FastAPI 接口层 |

## 多刃地形剖面处理

多刃是在单刃内核之上**新增的一层**，不改动旧接口。输入是沿收发路径按里程排列的整条地形剖面：每个采样点只带 `(distance_m, elevation_m)`（到发射端里程、地面海拔），另给收发两端的地面海拔与天线架设高度、频率与链路总长。两端天线顶的连线即直视线，每个采样点相对直视线的超出高度由服务自行折算，调用方无需预先折算。采样点之间不做地形插值。

主障碍按业界处理串联多刃的标准手法之一——**Deygout 主障碍递归法**逐层选出：

1. 在当前子链路上，以该段两端点（天线顶或上一级山顶）连线为参考直视线，对每个候选采样点用**单刃内核**算
   `v = h·sqrt(2·(d1+d2)/(λ·d1·d2))`，距离取该点到本子链路两端的距离；
2. 取 **v 最大**（遮挡最重）的点作为本段主障碍——不是海拔最高、也不是离端点最近；
3. 主障碍把该段切成左右两段子链路，端点参考海拔取主障碍山顶，递归重复；某段内没有点高出其参考线（最大 v ≤ 0）即停止。

每个被选中的障碍都在**自己所属子链路**的几何下复用 `fresnel_parameter` / `knife_edge_loss_db` 算自己那份损耗；总附加损耗按 Deygout 级联口径把各刃分量在 dB 域相加 `Σ J(v_i)`。退化性质：只有一处凸起时结果与单刃接口逐位一致；全程通视（没有点咬进直视线）时总损耗为 0，绝不因地形起伏凭空累加。

## 接口

- `POST /v1/diffraction/parameters` — 输入几何与频率，返回 `v`、`clearance_m`、`clearance_fresnel_ratio`、`first_fresnel_radius_m`、`wavelength_m`。
- `POST /v1/diffraction/assessment` — 同样输入，追加 `loss_db` 与 `is_los`。
- `POST /v1/diffraction/batch` — `{"links": [...]}` 一批单刃链路一次算完，各条结果独立，单条不合法只在该条返回错误。
- `POST /v1/multiedge/assessment` — 输入整条地形剖面与两端天线参数，返回 `total_loss_db`、`is_los`、`obstacle_count` 与 `obstacles` 明细（每个被选中障碍的采样点位置、所在子链路几何、相对该段参考线的 `v` 与该份 `loss_db`）。
- `POST /v1/multiedge/batch` — `{"links": [...]}` 多条剖面成组评估，各条独立、互不覆盖，单条校验失败只在自己的结果里报错。
- `GET /v1/examples/ridge` — 预置的山脊略微遮挡算例（损耗 ≈ 10 dB > 6 dB）。
- `GET /healthz` — 存活探针。

多刃请求体形如：

```json
{
  "link_id": "link-a",
  "frequency_mhz": 900.0,
  "path_length_m": 10000.0,
  "tx": {"ground_elevation_m": 0.0, "antenna_height_m": 10.0},
  "rx": {"ground_elevation_m": 100.0, "antenna_height_m": 10.0},
  "profile": [
    {"distance_m": 500.0,  "elevation_m": 26.0},
    {"distance_m": 3000.0, "elevation_m": 80.0}
  ]
}
```

`profile` 允许为空（全程通视）；里程必须严格递增且严格位于收发之间；天线高度非负；海拔、频率、链路长度须为有限数值。

输入不合法（距离/频率非正、非有限数）返回 `400` 与带原因的错误 JSON：

```json
{"error": {"code": "INVALID_INPUT", "reason": "d1_m 必须为正数，收到 0.0"}}
```

## 本地运行

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080
pytest
```

## Docker

```bash
docker build -t knife-edge-diffraction .
docker run --rm -p 8080:8080 knife-edge-diffraction      # 服务挂在固定端口 8080
docker run --rm knife-edge-diffraction pytest            # 在容器内执行测试
```

## 测试重点

`tests/` 用自动化测试钉住以下关系：

- 擦边 `h=0`：`v=0`，附加损耗约 6 dB；
- 只加高障碍：损耗随之升高；
- 只把频率加倍：同一几何下 `v` 变为原来的 √2 倍；
- `d1=d2` 且障碍显著低于直视线：损耗趋零、判定通视；
- 批量调用各条独立、互不覆盖；非法输入返回带原因的错误 JSON。

多刃部分（`test_profile.py`、`test_multiedge.py`、`test_profile_batch.py`、`test_multiedge_api.py`）额外钉死四条关键关系：

1. **退化一致**：仅一处凸起（其余点在直视线下方）时，多刃总损耗与选中障碍的 `v`/损耗与把该凸起单独喂给单刃接口逐位一致（水平与倾斜直视线各一例）；
2. **通视归零**：所有采样点都在直视线下方（含空剖面、起伏地形）时总损耗为 0 且判为通视，不选中任何障碍；
3. **主障碍取最大 v**：倾斜直视线的算例中，海拔最高点与距发射端最近点都不是主障碍，被选中的是菲涅尔参数最大的点；
4. **抬高单调**：在已有凸起的剖面上只抬高其中一处（含叶障碍与跨越主/次身份翻转），合成总损耗不减。

另覆盖：子链路参考线与 d1/d2 取自所属分段、三级递归、总损耗为各刃 dB 之和、采样点里程严格递增/落在收发之间、天线高度非负、批量错误隔离，以及上千采样点（含每点都被选中的最坏凹形剖面）的规模。
