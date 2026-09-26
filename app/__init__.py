"""刃形绕射损耗计算服务。

单刃内核与新增的多刃地形剖面层，均经 HTTP 暴露。
模块划分：
- geometry          单刃链路几何与余隙
- fresnel           菲涅尔-基尔霍夫参数 v、波长换算（单/多刃共用内核）
- zone              第一菲涅尔区半径
- loss              附加损耗近似（ITU-R P.526 刃形绕射，单/多刃共用内核）
- validation        单刃输入校验
- service           单刃评估编排
- batch             单刃批量调度
- presets           预置算例
- schemas           单刃接口数据模型
- profile           地形剖面表示、直视线余隙折算与剖面校验
- multiedge         主障碍递归选取（Deygout 主障碍法）与分段
- synthesis         多刃损耗级联合成
- profile_service   多刃剖面评估编排
- profile_batch     多刃批量调度
- profile_schemas   多刃接口数据模型
- main              FastAPI 接口层
"""
