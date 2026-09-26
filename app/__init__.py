"""刃形绕射损耗计算服务。

单刃绕射内核与多刃（地形剖面）级联评估，经 HTTP 暴露。
模块划分：
- geometry           链路几何与余隙
- fresnel            菲涅尔-基尔霍夫参数 v
- zone               第一菲涅尔区半径
- loss               附加损耗近似（ITU-R P.526 刃形绕射）
- validation         输入校验
- service            单刃评估编排
- batch              单刃批量调度
- presets            预置算例
- profile            地形剖面的表示与余隙折算
- multiedge          主障碍的递归选取与分段（Deygout 级联）
- combine            多刃损耗的合成
- profile_validation 剖面输入校验
- profile_service    多刃剖面评估编排
- profile_batch      多刃剖面批量调度
- schemas            接口数据模型
- main               FastAPI 接口层
"""
