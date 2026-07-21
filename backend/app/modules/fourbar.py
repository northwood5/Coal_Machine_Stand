"""掩护式支架四连杆机构运动学求解与优化。

平面简化模型 (底座坐标系, x 向采空区为负/向煤壁为正, y 向上, 单位 mm):

  - 后连杆: 下铰点 A 固定于底座, 上铰点 C 在掩护梁上
  - 前连杆: 下铰点 B 固定于底座, 上铰点 D 在掩护梁上
  - 掩护梁: 刚体, 含 C、D 及与顶梁的铰点 E (梁端最高点)
    梁轴线方向单位向量 u, E = C + lc*u, D = C + (lc-ld)*u

运动学: 给定后连杆摆角 φ → C 确定 → 由 |D-B|=Lb 解掩护梁倾角 θ → E 轨迹。
顶梁前端 x 坐标随支架升降形成"双纽线", 其宽度是四连杆设计的核心指标。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import brentq, minimize


@dataclass
class LinkageGeometry:
    A: tuple[float, float]      # 后连杆下铰点
    B: tuple[float, float]      # 前连杆下铰点
    La: float                   # 后连杆长
    Lb: float                   # 前连杆长
    lc: float                   # C 到 E 沿掩护梁距离
    ld: float                   # D 到 E 沿掩护梁距离 (ld < lc)


_THETA_GRID = np.linspace(0.15, 1.45, 48)
_COS_G, _SIN_G = np.cos(_THETA_GRID), np.sin(_THETA_GRID)


def _solve_theta(C: np.ndarray, B: np.ndarray, arm: float, Lb: float) -> float | None:
    """解掩护梁倾角 θ: |C + arm*u(θ) - B| = Lb, u = (cosθ, sinθ)  (向量化扫描 + brentq 精解)"""
    dx = C[0] + arm * _COS_G - B[0]
    dy = C[1] + arm * _SIN_G - B[1]
    vals = np.hypot(dx, dy) - Lb
    sign_change = np.where(vals[:-1] * vals[1:] <= 0)[0]
    if len(sign_change) == 0:
        return None

    def f(theta: float) -> float:
        return float(math_hypot(C[0] + arm * np.cos(theta) - B[0],
                                C[1] + arm * np.sin(theta) - B[1]) - Lb)

    i = int(sign_change[0])
    try:
        return float(brentq(f, _THETA_GRID[i], _THETA_GRID[i + 1], xtol=1e-9))
    except ValueError:
        return None


def math_hypot(a: float, b: float) -> float:
    return (a * a + b * b) ** 0.5


def sweep(geom: LinkageGeometry, n: int = 80,
          phi_range: tuple[float, float] = (0.5, 2.2)) -> dict:
    """扫掠后连杆摆角, 返回 E 点轨迹与各杆角度。

    返回 dict: phi[], theta[], Ex[], Ey[] (仅保留有解的位形)
    """
    A = np.array(geom.A, dtype=float)
    B = np.array(geom.B, dtype=float)
    arm = geom.lc - geom.ld

    out = {"phi": [], "theta": [], "Ex": [], "Ey": []}
    for phi in np.linspace(phi_range[0], phi_range[1], n):
        C = A + geom.La * np.array([np.cos(phi), np.sin(phi)])
        theta = _solve_theta(C, B, arm, geom.Lb)
        if theta is None:
            continue
        u = np.array([np.cos(theta), np.sin(theta)])
        E = C + geom.lc * u
        out["phi"].append(float(phi))
        out["theta"].append(float(theta))
        out["Ex"].append(float(E[0]))
        out["Ey"].append(float(E[1]))
    return out


def lemniscate_width(geom: LinkageGeometry, h_min: float, h_max: float,
                     n: int = 80) -> tuple[float | None, dict]:
    """支撑高度范围 [h_min, h_max] 内 E 点水平摆动量 (双纽线宽度)。

    h_min/h_max 为支撑高度, 内部换算为 E 点高度 (×HEIGHT_TO_EY)。
    返回 (width_mm | None, sweep_data)。None 表示该几何无法覆盖高度范围。
    """
    ey_lo, ey_hi = HEIGHT_TO_EY * h_min, HEIGHT_TO_EY * h_max
    data = sweep(geom, n=n)
    if len(data["Ey"]) < 5:
        return None, data
    ey = np.array(data["Ey"])
    ex = np.array(data["Ex"])
    if ey.max() < ey_hi or ey.min() > ey_lo:
        return None, data          # 高度范围覆盖不了
    mask = (ey >= ey_lo) & (ey <= ey_hi)
    if mask.sum() < 3:
        return None, data
    return float(ex[mask].max() - ex[mask].min()), data


# 支撑高度 → 顶梁铰点 E 高度换算系数 (计入顶梁厚度)
HEIGHT_TO_EY = 0.88


def initial_guess(h_min: float, h_max: float) -> LinkageGeometry:
    """按可行性搜索得到的经验比例给初始几何 (以最大支撑高度为特征尺寸)。

    比例经数值搜索验证可覆盖 h_min/h_max≈0.48 的高度比;
    优化器将在此基础上最小化双纽线宽度。
    """
    H = h_max
    return LinkageGeometry(
        A=(0.0, 0.064 * H),
        B=(0.284 * H, 0.095 * H),
        La=0.26 * H,
        Lb=0.33 * H,
        lc=0.745 * H,
        ld=(0.745 - 0.189) * H,
    )


# 经验最优比例中心 (以 h_max 为特征尺寸; 数值搜索+抛光获得, 适配采高比~0.5)
_GOOD_RATIOS = np.array([0.031, 0.075, 0.110, 0.319, 0.277, 0.794, 0.738])
#                        Ay     Bx     By     La     Lb     lc     ld

_opt_cache: dict[tuple[int, int], tuple] = {}


def optimize_linkage(h_min: float, h_max: float,
                     seed: int = 7) -> tuple[LinkageGeometry, float, dict]:
    """优化四连杆几何, 最小化双纽线宽度。

    两阶段: ① 围绕经验比例的定向随机搜索 (探全局)
           ② 多重启 Nelder-Mead 抛光 (收局部)
    设计变量: [Ay, Bx, By, La, Lb, lc, ld] (Ax=0 为基准, 消除平移自由度)
    返回 (最优几何, 宽度 mm, 轨迹数据)
    """
    key = (round(h_min), round(h_max))
    if key in _opt_cache:
        return _opt_cache[key]

    H = h_max
    ey_lo, ey_hi = HEIGHT_TO_EY * h_min, HEIGHT_TO_EY * h_max

    def build(x: np.ndarray) -> LinkageGeometry:
        return LinkageGeometry(A=(0.0, x[0]), B=(x[1], x[2]),
                               La=x[3], Lb=x[4], lc=x[5], ld=x[6])

    def objective(x: np.ndarray, n: int = 40) -> float:
        if x[6] <= 0.02 * H or x[5] <= x[6] + 0.02 * H:      # ld>0 且 lc>ld
            return 1e6
        if x[3] <= 0.08 * H or x[4] <= 0.08 * H:
            return 1e6
        w, data = lemniscate_width(build(x), h_min, h_max, n=n)
        if w is not None:
            return w
        if not data["Ey"]:
            return 1e5
        ey = np.array(data["Ey"])
        shortfall = max(0.0, ey_hi - ey.max()) + max(0.0, ey.min() - ey_lo)
        return 2e4 + shortfall                                # 平滑罚引导回可行域

    rng = np.random.default_rng(seed)

    # 阶段①: 定向随机搜索
    best_x, best_f = _GOOD_RATIOS * H, objective(_GOOD_RATIOS * H)
    for _ in range(400):
        x = _GOOD_RATIOS * H * rng.uniform(0.7, 1.3, size=7)
        f = objective(x, n=32)
        if f < best_f:
            best_x, best_f = x, f

    # 阶段②: 多重启抛光
    def polish(x_init: np.ndarray, f_init: float, restarts: int = 3):
        bx, bf = x_init, f_init
        for trial in range(restarts):
            xs = bx if trial == 0 else bx * rng.uniform(0.97, 1.03, size=7)
            res = minimize(objective, xs, method="Nelder-Mead",
                           options={"maxiter": 600, "xatol": 0.5, "fatol": 0.05})
            if res.fun < bf:
                bx, bf = res.x, res.fun
        return bx, bf

    best_x, best_f = polish(best_x, best_f)

    # 阶段③: 结果不理想时扩大范围重搜一轮
    if best_f > 70.0:
        for _ in range(800):
            x = _GOOD_RATIOS * H * rng.uniform(0.5, 1.5, size=7)
            f = objective(x, n=32)
            if f < best_f:
                best_x, best_f = x, f
        best_x, best_f = polish(best_x, best_f, restarts=4)

    best = build(best_x)
    w, data = lemniscate_width(best, h_min, h_max)
    if w is None:                                             # 兜底: 退回经验比例
        best = build(_GOOD_RATIOS * H)
        w, data = lemniscate_width(best, h_min, h_max)
    out = (best, (w if w is not None else float("inf")), data)
    _opt_cache[key] = out
    return out


def pose_at_height(geom: LinkageGeometry, height: float) -> dict | None:
    """给定支撑高度, 返回该位形下各铰点坐标与杆件角度 (受力分析用)"""
    target_ey = HEIGHT_TO_EY * height
    data = sweep(geom, n=160)
    if not data["Ey"]:
        return None
    ey = np.array(data["Ey"])
    idx = int(np.argmin(np.abs(ey - target_ey)))
    if abs(ey[idx] - target_ey) > 0.05 * target_ey:
        return None
    phi, theta = data["phi"][idx], data["theta"][idx]
    A = np.array(geom.A)
    B = np.array(geom.B)
    C = A + geom.La * np.array([np.cos(phi), np.sin(phi)])
    u = np.array([np.cos(theta), np.sin(theta)])
    E = C + geom.lc * u
    D = C + (geom.lc - geom.ld) * u
    return {
        "phi": phi, "theta": theta,
        "A": A.tolist(), "B": B.tolist(), "C": C.tolist(),
        "D": D.tolist(), "E": E.tolist(),
        # 两力杆方向单位向量 (由下铰点指向上铰点)
        "rear_dir": ((C - A) / np.linalg.norm(C - A)).tolist(),
        "front_dir": ((D - B) / np.linalg.norm(D - B)).tolist(),
    }
