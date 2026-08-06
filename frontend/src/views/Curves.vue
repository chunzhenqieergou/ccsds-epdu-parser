<template>
  <div class="curves-page">
    <div class="page-header">
      <h3 class="page-title">曲线绘制</h3>
      <p class="page-desc">实时遥测曲线 & 历史数据曲线</p>
    </div>

    <el-tabs v-model="activeTab" type="border-card">
      <el-tab-pane label="实时曲线" name="realtime">
        <div class="toolbar">
          <el-select
            v-model="selectedParams"
            multiple
            filterable
            placeholder="请选择遥测参数"
            style="width: 400px"
            collapse-tags
            collapse-tags-tooltip
            @change="onParamsChange"
          >
            <el-option
              v-for="p in paramList"
              :key="p.id"
              :label="p.param_code + ' (' + (p.name || p.param_code) + ')'"
              :value="p.param_code"
            />
          </el-select>
          <el-tag v-if="realtimeConnected" type="success" size="small">已连接</el-tag>
          <el-tag v-else type="danger" size="small">未连接</el-tag>
          <el-button @click="exportPng('realtime')" :disabled="!realtimeReady" size="small">导出图片</el-button>
        </div>
        <div ref="realtimeChartRef" class="chart-container"></div>
      </el-tab-pane>

      <el-tab-pane label="历史曲线" name="history">
        <div class="toolbar">
          <el-select
            v-model="historyParams"
            multiple
            filterable
            placeholder="请选择遥测参数"
            style="width: 400px"
            collapse-tags
            collapse-tags-tooltip
          >
            <el-option
              v-for="p in paramList"
              :key="p.id"
              :label="p.param_code + ' (' + (p.name || p.param_code) + ')'"
              :value="p.param_code"
            />
          </el-select>
          <el-date-picker
            v-model="historyTimeRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            value-format="YYYY-MM-DD HH:mm:ss"
          />
          <el-button type="primary" @click="queryHistory" :loading="historyLoading">查询</el-button>
          <el-button @click="exportPng('history')" :disabled="!historyReady" size="small">导出图片</el-button>
        </div>
        <div ref="historyChartRef" class="chart-container"></div>
      </el-tab-pane>

      <el-tab-pane label="仪表盘" name="gauge">
        <div class="toolbar">
          <el-select
            v-model="gaugeParams"
            multiple
            filterable
            placeholder="请选择要监控的参数"
            style="width: 400px"
            collapse-tags
            collapse-tags-tooltip
          >
            <el-option
              v-for="p in paramList"
              :key="p.id"
              :label="p.param_code + ' (' + (p.name || p.param_code) + ')'"
              :value="p.param_code"
            />
          </el-select>
          <el-switch v-model="gaugeAuto" active-text="自动刷新" @change="onGaugeAutoChange" />
          <el-button @click="refreshGauges" :loading="gaugeLoading" size="small">刷新</el-button>
          <el-tag v-if="gaugeLastUpdate" size="small" type="info">
            更新于 {{ dayjs(gaugeLastUpdate).format('HH:mm:ss') }}
          </el-tag>
        </div>
        <el-empty v-if="gaugeParams.length === 0" description="请选择要监控的遥测参数" />
        <div v-else class="gauge-grid">
          <div v-for="code in gaugeParams" :key="code" class="gauge-item">
            <div :ref="(el) => setGaugeRef(el, code)" class="gauge-box"></div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import { paramApi } from '../api/satellite'
import { telemetryApi } from '../api/telemetry'
import { useEcharts } from '../composables/useEcharts'

const activeTab = ref('realtime')

const paramList = ref([])
const selectedParams = ref([])
const historyParams = ref([])
const gaugeParams = ref([])
const gaugeAuto = ref(false)
const gaugeLoading = ref(false)
const gaugeLastUpdate = ref(null)

const realtimeChartRef = ref(null)
const historyChartRef = ref(null)

const realtimeReady = ref(false)
const historyReady = ref(false)
const historyLoading = ref(false)
const realtimeConnected = ref(false)

const historyTimeRange = ref([])

const {
  chartInstance: realtimeChart,
  setOption: setRealtimeOption,
  getInstance: getRealtimeInstance,
  resize: resizeRealtime
} = useEcharts(realtimeChartRef)

const {
  chartInstance: historyChart,
  setOption: setHistoryOption,
  getInstance: getHistoryInstance
} = useEcharts(historyChartRef)

const MAX_POINTS = 600               // 单参数最多保留的点数
const realtimeSeriesMap = ref({})    // { [param_code]: Map<tsMs, value> }
let lastCursorMs = 0                 // 已经收到过的最大 ts（毫秒），用于增量拉取
let pollTimer = null                 // 轮询定时器句柄
let seriesColors = ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272', '#fc8452', '#9a60b4', '#ea7ccc']

// ---- 仪表盘状态 ----
const gaugeEls = {}                  // code -> DOM
const gaugeInstances = {}            // code -> echarts 实例
let gaugeTimer = null

async function fetchParams() {
  try {
    const data = await paramApi.list({ page: 1, page_size: 100 })
    paramList.value = Array.isArray(data) ? data : (data.items || [])
  } catch {}
}

// ISO / 数字 / Date 等统一为毫秒数；ECharts time 轴只认数字
function tsToMs(ts) {
  if (ts == null || ts === '') return Date.now()
  if (typeof ts === 'number') return ts < 1e12 ? ts * 1000 : ts
  const d = new Date(String(ts).replace(' ', 'T'))
  return isNaN(d.getTime()) ? Date.now() : d.getTime()
}

function onParamsChange() {
  if (activeTab.value === 'realtime') {
    // 切换参数时清空数据和游标，避免残留
    realtimeSeriesMap.value = {}
    lastCursorMs = 0
    initRealtimeChart()
    startPolling()
  }
}

function buildRealtimeOption() {
  const codes = selectedParams.value
  const series = codes.map((code, i) => {
    const map = realtimeSeriesMap.value[code]
    const arr = map
      ? [...map.entries()].sort((a, b) => a[0] - b[0]).map(([t, v]) => [t, Number(v)])
      : []
    return {
      name: code,
      type: 'line',
      data: arr,
      smooth: arr.length >= 20,         // 点太少时不平滑，避免出现诡异弧线
      showSymbol: arr.length <= 60,    // 稀疏时显示圆点
      sampling: arr.length > 200 ? 'lttb' : false, // 点很多时降采样，曲线更平滑
      connectNulls: false,
      lineStyle: { width: 2 },
      itemStyle: { color: seriesColors[i % seriesColors.length] }
    }
  })
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: codes, bottom: 4 },
    grid: { left: 60, right: 24, top: 28, bottom: 64 },
    xAxis: {
      type: 'time',
      axisLabel: { formatter: (v) => dayjs(v).format('HH:mm:ss') }
    },
    yAxis: {
      type: 'value',
      name: '数值',
      scale: true,
      splitLine: { lineStyle: { type: 'dashed' } }
    },
    dataZoom: [
      { type: 'inside' },
      { type: 'slider', height: 18, bottom: 24 }
    ],
    series
  }
}

function initRealtimeChart() {
  // 确保每个被选中的参数都有一个 Map
  selectedParams.value.forEach((code) => {
    if (!realtimeSeriesMap.value[code]) {
      realtimeSeriesMap.value[code] = new Map()
    }
  })
  // 始终 notMerge=true，避免 dataZoom / tooltip 等配置叠加错位
  setRealtimeOption(buildRealtimeOption(), true)
  realtimeReady.value = selectedParams.value.length > 0
}

async function pollLatest() {
  if (!selectedParams.value.length) return
  try {
    const nowMs = Date.now()
    // 首次进入给 5 秒缓冲，避免首轮游标挡住已有数据
    const cursor = lastCursorMs || (nowMs - 5000)
    const data = await telemetryApi.query({
      param_codes: selectedParams.value,
      start: dayjs(cursor).format('YYYY-MM-DD HH:mm:ss'),
      end: dayjs(nowMs).format('YYYY-MM-DD HH:mm:ss'),
      page_size: 1000
    })
    const items = Array.isArray(data)
      ? data
      : (data.points || data.items || data.records || [])

    let touched = false
    for (const item of items) {
      const code = item.param_code
      if (!code) continue
      if (!realtimeSeriesMap.value[code]) {
        realtimeSeriesMap.value[code] = new Map()
      }
      const ms = tsToMs(item.ts || item.timestamp || item.time || item.created_at)
      // 游标过滤 + Map 去重：同一 ts 多次到达只保留最新
      if (ms <= cursor) continue
      if (realtimeSeriesMap.value[code].get(ms) !== undefined) continue

      realtimeSeriesMap.value[code].set(ms, Number(item.value))
      if (ms > lastCursorMs) lastCursorMs = ms
      touched = true

      // 超过上限时丢弃最早的数据
      const m = realtimeSeriesMap.value[code]
      if (m.size > MAX_POINTS) {
        const keys = [...m.keys()].sort((a, b) => a - b)
        const drop = keys.length - MAX_POINTS
        for (let k = 0; k < drop; k++) m.delete(keys[k])
      }
    }
    if (touched) setRealtimeOption(buildRealtimeOption(), true)
    realtimeConnected.value = true
  } catch {
    realtimeConnected.value = false
  }
}

function startPolling() {
  stopPolling()
  pollLatest()
  pollTimer = setInterval(pollLatest, 1000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function queryHistory() {
  if (!historyParams.value.length || !historyTimeRange.value?.length) {
    ElMessage.warning('请选择参数和时间范围')
    return
  }
  historyLoading.value = true
  try {
    const [start, end] = historyTimeRange.value
    const data = await telemetryApi.query({
      param_codes: historyParams.value,
      start,
      end,
      sampling: 'auto',
      page_size: 1000,
      max_points: 3000
    })
    const items = Array.isArray(data) ? data : (data.points || data.items || data.records || [])
    const seriesMap = {}
    historyParams.value.forEach(code => { seriesMap[code] = [] })
    items.forEach(item => {
      const code = item.param_code
      if (seriesMap[code]) {
        const ts = item.ts || item.timestamp || item.time || item.created_at
        seriesMap[code].push([ts, Number(item.value)])
      }
    })
    const series = historyParams.value.map((code, i) => ({
      name: code,
      type: 'line',
      data: seriesMap[code] || [],
      smooth: true,
      showSymbol: false,
      lineStyle: { width: 2 },
      itemStyle: { color: seriesColors[i % seriesColors.length] }
    }))
    setHistoryOption({
      tooltip: { trigger: 'axis' },
      legend: { data: historyParams.value, bottom: 0 },
      grid: { left: 60, right: 30, top: 30, bottom: 50 },
      xAxis: { type: 'time' },
      yAxis: { type: 'value', name: '数值', splitLine: { lineStyle: { type: 'dashed' } } },
      dataZoom: [
        { type: 'inside', start: 0, end: 100 },
        { type: 'slider', start: 0, end: 100, height: 20, bottom: 22 }
      ],
      series
    }, true)
    historyReady.value = true
  } catch {
  } finally {
    historyLoading.value = false
  }
}

function exportPng(mode) {
  const instance = mode === 'realtime' ? getRealtimeInstance() : getHistoryInstance()
  if (!instance) {
    ElMessage.warning('暂无图表数据')
    return
  }
  const url = instance.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#fff' })
  const a = document.createElement('a')
  a.href = url
  a.download = `遥测曲线_${dayjs().format('YYYYMMDD_HHmmss')}.png`
  a.click()
  ElMessage.success('图片已导出')
}

// ===================================================================
// 仪表盘（ECharts gauge）
// ===================================================================
function setGaugeRef(el, code) {
  if (el) {
    gaugeEls[code] = el
  }
}

function buildGaugeOption(meta, value) {
  const unit = meta?.unit || ''
  const tMin = meta?.threshold_min != null ? Number(meta.threshold_min) : null
  const tMax = meta?.threshold_max != null ? Number(meta.threshold_max) : null

  // 量程推导：优先用阈值范围；否则以当前值为中心外扩
  let min, max
  if (tMin != null && tMax != null) {
    min = tMin
    max = tMax
  } else if (tMax != null) {
    min = value != null ? Math.min(0, value - Math.abs(tMax - value) * 0.5) : 0
    max = tMax
  } else {
    min = value != null ? value * 0.8 : 0
    max = value != null ? value * 1.2 : 100
  }
  if (max - min < 1e-6) max = min + 1

  // 阈值色带：低限以下红 → 正常绿 → 高限以上红
  const range = max - min
  const seg = []
  if (tMin != null && tMin > min) seg.push([(tMin - min) / range, '#F56C6C'])
  const midEnd = tMax != null ? (tMax - min) / range : 1
  seg.push([Math.max(seg.length ? seg[seg.length - 1][0] : 0, midEnd), '#67C23A'])
  if (tMax != null && tMax < max) seg.push([1, '#F56C6C'])

  return {
    series: [
      {
        type: 'gauge',
        min,
        max,
        startAngle: 210,
        endAngle: -30,
        radius: '70%',
        center: ['50%', '58%'],
        splitNumber: 12,
        progress: { show: true, width: 14, roundCap: true },
        axisLine: { lineStyle: { width: 14, color: seg } },
        axisTick: { distance: -18, length: 7, lineStyle: { color: '#909399', width: 1.5 } },
        splitLine: {
          distance: -22,
          length: 14,
          lineStyle: { color: '#909399', width: 1.5 }
        },
        axisLabel: {
          distance: -28,
          fontSize: 12,
          color: '#666',
          formatter: (v) => (Math.abs(v) >= 100 ? String(Math.round(v)) : v.toFixed(1))
        },
        pointer: { width: 5, length: '60%' },
        anchor: { show: true, size: 9, itemStyle: { color: '#909399' } },
        title: {
          offsetCenter: [0, '85%'],
          fontSize: 13,
          color: '#555'
        },
        detail: {
          valueAnimation: true,
          formatter: (v) => (value == null ? '-' : v.toFixed(2)),
          fontSize: 20,
          fontWeight: 500,
          color: value == null ? '#bbb' : (value > (tMax ?? Infinity) || value < (tMin ?? -Infinity) ? '#F56C6C' : '#303133'),
          offsetCenter: [0, '60%']
        },
        data: [{ value: value ?? min, name: `${meta?.name || code}${unit ? ' (' + unit + ')' : ''}` }]
      }
    ]
  }
}

function renderGauge(code, meta, value) {
  const el = gaugeEls[code]
  if (!el) return
  if (!gaugeInstances[code]) {
    gaugeInstances[code] = echarts.init(el)
  }
  gaugeInstances[code].setOption(buildGaugeOption(meta, value), true)
}

async function refreshGauges() {
  if (!gaugeParams.value.length) return
  gaugeLoading.value = true
  try {
    const data = await telemetryApi.latest()
    const items = Array.isArray(data) ? data : (data.data || [])
    const latestMap = {}
    items.forEach((it) => {
      latestMap[it.param_code] = it
    })
    gaugeParams.value.forEach((code) => {
      const meta = paramList.value.find((p) => (p.param_code || p.code) === code)
      const cur = latestMap[code]
      renderGauge(code, meta, cur ? Number(cur.value) : null)
    })
    gaugeLastUpdate.value = Date.now()
  } catch {
    // 网络异常时保留上次数据
  } finally {
    gaugeLoading.value = false
  }
}

function onGaugeAutoChange(val) {
  if (val) {
    refreshGauges()
    gaugeTimer = setInterval(refreshGauges, 2000)
  } else if (gaugeTimer) {
    clearInterval(gaugeTimer)
    gaugeTimer = null
  }
}

function stopGaugeAuto() {
  if (gaugeTimer) {
    clearInterval(gaugeTimer)
    gaugeTimer = null
  }
  Object.values(gaugeInstances).forEach((inst) => inst.dispose())
  Object.keys(gaugeInstances).forEach((k) => delete gaugeInstances[k])
}

watch(activeTab, async (tab) => {
  if (tab === 'gauge') {
    await nextTick()
    // tab 切换后 DOM 可见，重建实例避免 0 尺寸
    Object.values(gaugeInstances).forEach((inst) => inst.dispose())
    Object.keys(gaugeInstances).forEach((k) => delete gaugeInstances[k])
    refreshGauges()
  }
})

onMounted(async () => {
  await fetchParams()
})

onUnmounted(() => {
  stopPolling()
  stopGaugeAuto()
})
</script>

<style scoped>
.curves-page { max-width: 1400px; }
.page-header { margin-bottom: 16px; }
.page-title { margin: 0 0 4px; font-size: 20px; color: #1a1a2e; }
.page-desc { margin: 0; color: #999; font-size: 14px; }
.toolbar { display: flex; align-items: center; gap: 12px; padding: 12px 0; flex-wrap: wrap; }
.chart-container { width: 100%; height: 520px; }
.gauge-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 14px;
  padding: 12px 0;
}
.gauge-item {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  padding: 4px;
}
.gauge-box {
  width: 100%;
  height: 300px;
}
</style>
