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
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
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

const MAX_POINTS = 300
const realtimeSeriesData = ref({})
let pollTimer = null
let seriesColors = ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272', '#fc8452', '#9a60b4', '#ea7ccc']

async function fetchParams() {
  try {
    const data = await paramApi.list({ page: 1, page_size: 100 })
    paramList.value = Array.isArray(data) ? data : (data.items || [])
  } catch {}
}

function onParamsChange() {
  if (activeTab.value === 'realtime') {
    initRealtimeChart()
    startPolling()
  }
}

function buildRealtimeOption() {
  const series = selectedParams.value.map((code, i) => ({
    name: code,
    type: 'line',
    data: realtimeSeriesData.value[code] || [],
    smooth: true,
    showSymbol: false,
    lineStyle: { width: 2 },
    itemStyle: { color: seriesColors[i % seriesColors.length] }
  }))
  return {
    tooltip: { trigger: 'axis', formatter: (params) => {
      let html = dayjs(params[0].axisValue).format('HH:mm:ss') + '<br/>'
      params.forEach(p => { html += `${p.marker}${p.seriesName}: ${p.value}<br/>` })
      return html
    }},
    legend: { data: selectedParams.value, bottom: 0 },
    grid: { left: 60, right: 30, top: 30, bottom: 50 },
    xAxis: { type: 'time', axisLabel: { formatter: (v) => dayjs(v).format('HH:mm:ss') } },
    yAxis: { type: 'value', name: '数值', splitLine: { lineStyle: { type: 'dashed' } } },
    dataZoom: [
      { type: 'inside', start: 0, end: 100 },
      { type: 'slider', start: 0, end: 100, height: 20, bottom: 22 }
    ],
    series
  }
}

function initRealtimeChart() {
  selectedParams.value.forEach(code => {
    if (!realtimeSeriesData.value[code]) {
      realtimeSeriesData.value[code] = []
    }
  })
  const option = buildRealtimeOption()
  setRealtimeOption(option, true)
  realtimeReady.value = selectedParams.value.length > 0
}

async function pollLatest() {
  if (!selectedParams.value.length) return
  try {
    const now = dayjs().format('YYYY-MM-DD HH:mm:ss')
    const twoMinAgo = dayjs().subtract(2, 'minute').format('YYYY-MM-DD HH:mm:ss')
    const data = await telemetryApi.query({
      param_codes: selectedParams.value,
      start: twoMinAgo,
      end: now
    })
    const items = Array.isArray(data) ? data : (data.points || data.items || data.records || [])
    if (items.length) {
      items.forEach(item => {
        const code = item.param_code
        if (!realtimeSeriesData.value[code]) realtimeSeriesData.value[code] = []
        const ts = item.ts || item.timestamp || item.time || item.created_at || now
        realtimeSeriesData.value[code].push([ts, Number(item.value)])
        if (realtimeSeriesData.value[code].length > MAX_POINTS) {
          realtimeSeriesData.value[code].shift()
        }
      })
      setRealtimeOption(buildRealtimeOption(), false)
    }
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
      end
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

onMounted(async () => {
  await fetchParams()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.curves-page { max-width: 1400px; }
.page-header { margin-bottom: 16px; }
.page-title { margin: 0 0 4px; font-size: 20px; color: #1a1a2e; }
.page-desc { margin: 0; color: #999; font-size: 14px; }
.toolbar { display: flex; align-items: center; gap: 12px; padding: 12px 0; flex-wrap: wrap; }
.chart-container { width: 100%; height: 520px; }
</style>
