/**
 * 时序数据平滑工具
 *
 * 三种策略，按场景选用：
 *   - ewmaSmooth    流式指数加权移动平均，适合实时累积数据，O(n) 单次扫描
 *   - maSmooth      简单居中移动平均，窗口内均值，适合历史批量数据
 *   - sgSmooth      Savitzky-Golay 多项式拟合，保留波形特征 + 平滑噪声
 *
 * 设计目标：
 *   - 不破坏时间戳 [t, v] 配对顺序
 *   - 内部数值序列支持稀疏 / null / NaN，遇到缺失值保留或退化为简单平均
 *   - 函数全部 pure，不依赖 ECharts / DOM
 */

/* ---------------------------------------------------------------------------
 * 1. EWMA 指数加权移动平均（流式友好）
 *    s_0 = x_0
 *    s_t = α * x_t + (1 - α) * s_{t-1}
 *    α ∈ (0, 1]：越小越平滑，但滞后越大。0.3 是常用折中值
 * ------------------------------------------------------------------------- */
export function ewmaSmooth(values, alpha = 0.3) {
  if (!Array.isArray(values) || values.length === 0) return values
  const out = new Array(values.length)
  let prev = Number(values[0])
  out[0] = prev
  const a = Math.min(1, Math.max(0.01, Number(alpha) || 0.3))
  for (let i = 1; i < values.length; i++) {
    const v = values[i]
    if (v == null || Number.isNaN(Number(v))) {
      // 缺失：沿用上一个平滑值，避免断点抖动
      out[i] = prev
      continue
    }
    const cur = a * Number(v) + (1 - a) * prev
    out[i] = cur
    prev = cur
  }
  return out
}

/* ---------------------------------------------------------------------------
 * 2. 居中简单移动平均（批量友好）
 *    窗口大小建议取奇数，对称取均值。偶数窗口自动取 floor(n/2)
 * ------------------------------------------------------------------------- */
export function maSmooth(values, window = 5) {
  if (!Array.isArray(values) || values.length === 0) return values
  const w = Math.max(1, Math.floor(Number(window) || 1))
  if (w <= 1) return values.slice()
  const half = Math.floor(w / 2)
  const out = new Array(values.length)
  for (let i = 0; i < values.length; i++) {
    let sum = 0
    let n = 0
    for (let j = Math.max(0, i - half); j <= Math.min(values.length - 1, i + half); j++) {
      const v = values[j]
      if (v == null || Number.isNaN(Number(v))) continue
      sum += Number(v)
      n++
    }
    out[i] = n === 0 ? values[i] : sum / n
  }
  return out
}

/* ---------------------------------------------------------------------------
 * 3. Savitzky-Golay 平滑（保留波形特征的最佳选择）
 *
 *    核心：用最小二乘在每个滑动窗口内拟合一个低阶多项式，再取窗口中心的拟合值。
 *    相比 MA，SG 能在平滑噪声的同时更好地保留信号的峰、谷、拐点形状。
 *
 *    实现细节：
 *      - 窗口长度 w 必须为正奇数，传入偶数时自动 +1
 *      - 多项式阶数 k 默认 2（抛物线），w < k+2 时退化为 MA
 *      - 系数通过对 (X^T X) 做一次高斯消元得到，并按 (window, order) 缓存
 *      - 缺失值比例 > 20% 时降级为 MA 以保证数值稳定性
 *      - 边界点（窗口超出范围）按总权重归一化兜底，避免边界处幅度骤降
 * ------------------------------------------------------------------------- */

// 按 (window, order) 缓存 SG 卷积系数
const _sgCache = new Map()
function getSgCoeffs(window, order) {
  const key = `${window}:${order}`
  if (_sgCache.has(key)) return _sgCache.get(key)

  // 居中窗口 [-(m), ..., 0, ..., m]，m = (window-1)/2
  const m = Math.floor(window / 2)
  const cols = order + 1
  // 设计矩阵 X[i][j] = i^j
  const X = []
  for (let i = -m; i <= m; i++) {
    const row = new Array(cols)
    let pow = 1
    for (let j = 0; j < cols; j++) {
      row[j] = pow
      pow *= i
    }
    X.push(row)
  }
  // X^T X
  const XtX = Array.from({ length: cols }, () => new Array(cols).fill(0))
  for (let r = 0; r < cols; r++) {
    for (let c = 0; c < cols; c++) {
      let s = 0
      for (let i = 0; i < window; i++) s += X[i][r] * X[i][c]
      XtX[r][c] = s
    }
  }
  // (X^T X)^{-1}
  const inv = invertMatrix(XtX)
  if (!inv) return null

  // 中心一行的系数：coeff_i = Σ_j inv[0][j] * X[i][j]
  const coeffs = new Array(window).fill(0)
  for (let i = 0; i < window; i++) {
    let s = 0
    for (let j = 0; j < cols; j++) s += inv[0][j] * X[i][j]
    coeffs[i] = s
  }
  _sgCache.set(key, coeffs)
  return coeffs
}

// 高斯-约旦消元求逆
function invertMatrix(M) {
  const n = M.length
  const A = M.map((row, i) => [...row, ...Array.from({ length: n }, (_, j) => (i === j ? 1 : 0))])
  for (let i = 0; i < n; i++) {
    let pivot = i
    for (let k = i + 1; k < n; k++) {
      if (Math.abs(A[k][i]) > Math.abs(A[pivot][i])) pivot = k
    }
    if (Math.abs(A[pivot][i]) < 1e-12) return null
    if (pivot !== i) {
      const tmp = A[i]; A[i] = A[pivot]; A[pivot] = tmp
    }
    for (let k = i + 1; k < n; k++) {
      const factor = A[k][i] / A[i][i]
      if (factor === 0) continue
      for (let j = i; j < 2 * n; j++) A[k][j] -= factor * A[i][j]
    }
  }
  for (let i = n - 1; i >= 0; i--) {
    const div = A[i][i]
    for (let j = 0; j < 2 * n; j++) A[i][j] /= div
    for (let k = 0; k < i; k++) {
      const factor = A[k][i]
      if (factor === 0) continue
      for (let j = 0; j < 2 * n; j++) A[k][j] -= factor * A[i][j]
    }
  }
  const inv = Array.from({ length: n }, () => new Array(n).fill(0))
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) inv[i][j] = A[i][n + j]
  }
  return inv
}

export function sgSmooth(values, window = 5, order = 2) {
  if (!Array.isArray(values) || values.length === 0) return values
  let w = Math.floor(Number(window) || 5)
  if (w < 3) return values.slice()
  if (w % 2 === 0) w += 1
  const k = Math.min(Math.floor(Number(order) || 2), w - 2)
  if (k < 0) return values.slice()

  // 缺失值过多时退回 MA（数值稳定性更好）
  let missing = 0
  for (let i = 0; i < values.length; i++) {
    if (values[i] == null || Number.isNaN(Number(values[i]))) missing++
  }
  if (missing / values.length > 0.2) return maSmooth(values, w)

  const coeffs = getSgCoeffs(w, k)
  const m = Math.floor(w / 2)
  if (!coeffs) return maSmooth(values, w)

  const out = new Array(values.length)
  for (let i = 0; i < values.length; i++) {
    let acc = 0
    let totalWeight = 0
    for (let j = -m; j <= m; j++) {
      const idx = i + j
      if (idx < 0 || idx >= values.length) continue
      const v = values[idx]
      if (v == null || Number.isNaN(Number(v))) continue
      acc += coeffs[j + m] * Number(v)
      totalWeight += coeffs[j + m]
    }
    out[i] = Math.abs(totalWeight) < 1e-9 ? values[i] : acc / totalWeight
  }
  return out
}

/* ---------------------------------------------------------------------------
 * 4. 通用入口：作用于 [t, v] 点序列，保持时间戳不变
 *
 * opts:
 *   - method: 'ewma' | 'ma' | 'sg'   默认 'ewma'（流式稳定）
 *   - alpha: EWMA 平滑系数 (0,1]      默认 0.3
 *   - window: MA/SG 窗口，必须 ≥3     默认 5
 *   - order: SG 多项式阶数            默认 2
 *   - enabled: false 时原样返回       默认 true
 *   - medianWindow: 中值预滤波窗口，0 关闭  默认 0（默认不预滤波）
 *   - clipIqr: 是否启用 IQR 异常裁剪  默认 false
 *   - clipWindow: 局部 IQR 窗口大小   默认 21（奇数附近最佳）
 *   - clipK: 1.5 = 标准箱线图规则     默认 1.5
 *
 *   去噪链路执行顺序：
 *     中值预滤波（消除小幅振荡簇尖刺）
 *       → 局部 IQR 异常检测（消灭极端离群点）
 *       → 命中点 y 置 null
 *       → EWMA / SG / MA 拟合缺失段
 *       → ECharts bezier 平滑渲染
 * ------------------------------------------------------------------------- */
export function smoothSeries(points, opts = {}) {
  if (!Array.isArray(points) || points.length === 0) return points
  const {
    method = 'ewma',
    alpha = 0.3,
    window = 5,
    order = 2,
    enabled = true,
    medianWindow = 0,
    clipIqr = false,
    clipWindow = 21,
    clipK = 1.5
  } = opts
  if (!enabled) return points

  let pts = points
  let ys = pts.map((p) => (p == null ? null : p[1]))
  if (medianWindow > 0) {
    // 中值预滤波：直接对 y 序列去抖（不只用于 IQR 检测的中间步骤）
    ys = medianSmooth(ys, medianWindow)
  }
  if (clipIqr) {
    // IQR 在（已去抖的）y 上检测异常
    const mask = rollingIqrMask(ys, clipWindow, clipK)
    pts = clipOutliers(pts, mask)
    ys = pts.map((p) => (p == null ? null : p[1]))
  }

  let sm
  if (method === 'sg') sm = sgSmooth(ys, window, order)
  else if (method === 'ma') sm = maSmooth(ys, window)
  else sm = ewmaSmooth(ys, alpha)
  return points.map((p, i) => [p[0], sm[i]])
}

/**
 * 预定义的平滑档位（直接用于 UI 控件）
 */
export const SMOOTH_PRESETS = [
  { label: '关', value: 'off',   enabled: false },
  { label: '轻', value: 'light', method: 'sg', window: 5, order: 2, alpha: 0.5 },
  { label: '中', value: 'mid',   method: 'sg', window: 7, order: 2, alpha: 0.3 },
  { label: '重', value: 'heavy', method: 'sg', window: 11, order: 3, alpha: 0.2 }
]

/**
 * 把 SMOOTH_PRESETS 的档位转成 smoothSeries 用的 opts
 */
export function presetToOpts(preset) {
  if (!preset || preset.enabled === false) {
    return { enabled: false }
  }
  return {
    enabled: true,
    method: preset.method || 'ewma',
    alpha: preset.alpha,
    window: preset.window,
    order: preset.order
  }
}

/* ---------------------------------------------------------------------------
 * 5. 滚动 IQR 异常值检测 / 裁剪
 *
 *    问题场景：历史曲线中间出现一坨明显异常的"水滴"或"厚带"，
 *    通常是某段时间内数据值剧烈震荡 / 出现极端异常点。
 *    全局 IQR 容易被这一段异常拉宽阈值导致失效，
 *    所以采用局部（滑动窗口）IQR：每个点的判定只看它周围 ±half 区间。
 *
 *    算法：
 *      1. 对每个点 i，取窗口 [i-half, i+half] 内所有有效值
 *      2. 排序后取 Q1 / Q3，计算 IQR = Q3 - Q1
 *      3. 阈值 [Q1 - k·IQR, Q3 + k·IQR]，k=1.5 即经典箱线图规则
 *      4. 点值落在区间外 → 标记 false（当作 null 喂给后续平滑）
 *
 *    局限：
 *      - 窗口太小 (<5 有效点) 时跳过检测，避免误杀
 *      - 突变窗口（如阶跃）会被误判为异常。如有真实阶跃需求，
 *        可在调用方传入 preClip=false 关闭
 * ------------------------------------------------------------------------- */
export function rollingIqrMask(values, window = 21, k = 1.5) {
  if (!Array.isArray(values) || values.length === 0) return values.map(() => true)
  const mask = new Array(values.length).fill(true)
  const half = Math.max(1, Math.floor(window / 2))
  for (let i = 0; i < values.length; i++) {
    const v = values[i]
    if (v == null || Number.isNaN(Number(v))) {
      mask[i] = false
      continue
    }
    // 收集窗口内有效值
    const w = []
    for (let j = Math.max(0, i - half); j <= Math.min(values.length - 1, i + half); j++) {
      const wv = values[j]
      if (wv != null && !Number.isNaN(Number(wv))) w.push(Number(wv))
    }
    // 有效点太少，不做异常判定（信号本身稀疏，留给平滑自己处理）
    if (w.length < 5) continue
    const sorted = [...w].sort((a, b) => a - b)
    const q1 = sorted[Math.floor(sorted.length * 0.25)]
    const q3 = sorted[Math.floor(sorted.length * 0.75)]
    const iqr = q3 - q1
    // IQR=0（窗口内值全部相同）：放宽阈值为 ±1e-6 抖动，避免全部误杀
    const span = iqr > 0 ? iqr : 1e-6
    const lo = q1 - k * span
    const hi = q3 + k * span
    const n = Number(v)
    if (n < lo || n > hi) mask[i] = false
  }
  return mask
}

// 按 mask 把命中点 y 值置 null，保留时间戳不变（给上层 SG/MA 当缺失处理）
export function clipOutliers(points, mask) {
  if (!Array.isArray(points)) return points
  return points.map((p, i) => (mask[i] === false ? [p[0], null] : p))
}

/* ---------------------------------------------------------------------------
 * 6. 滑动中值滤波（pre-processing 去抖）
 *
 *    IQR 异常检测的盲区：低幅高频振荡簇
 *    比如一段数据是 [0, 1, 0, 1, 0, 1, ...]，单点既偏离整体也不极端，
 *    局部 IQR 完全检测不出来。但渲染时会糊成"水滴"。
 *
 *    中值滤波对这种簇天然免疫：取窗口中位，簇内点一律被替换为相邻中位值。
 *    缺点是会轻微钝化真实拐点（峰高略微降低），
 *    所以默认关闭，由上层 smoothSeries 在去噪链路中显式开启。
 * ------------------------------------------------------------------------- */
export function medianSmooth(values, window = 5) {
  if (!Array.isArray(values) || values.length === 0) return values
  const w = Math.max(2, Math.floor(Number(window) || 5))
  if (w <= 1) return values.slice()
  const half = Math.floor(w / 2)
  const out = new Array(values.length)
  for (let i = 0; i < values.length; i++) {
    const ww = []
    for (let j = Math.max(0, i - half); j <= Math.min(values.length - 1, i + half); j++) {
      const v = values[j]
      if (v != null && !Number.isNaN(Number(v))) ww.push(Number(v))
    }
    if (ww.length === 0) {
      out[i] = values[i]
    } else {
      ww.sort((a, b) => a - b)
      out[i] = ww[Math.floor(ww.length / 2)]
    }
  }
  return out
}
