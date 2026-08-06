<template>
  <div class="history-page">
    <h3 class="page-title">历史遥测数据查询</h3>

    <el-card class="query-card" shadow="never">
      <el-form :model="queryForm" inline>
        <el-form-item label="卫星">
          <el-select
            v-model="queryForm.satellite_id"
            placeholder="选择卫星"
            clearable
            style="width: 180px"
            @change="onSatelliteChange"
          >
            <el-option
              v-for="s in satellites"
              :key="s.id"
              :label="s.name || s.satellite_name"
              :value="s.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="参数">
          <el-select
            v-model="queryForm.param_codes"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            placeholder="选择参数"
            style="width: 260px"
          >
            <el-option
              v-for="p in paramOptions"
              :key="p.code"
              :label="`${p.code} - ${p.name}`"
              :value="p.code"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="queryForm.timeRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            format="YYYY-MM-DD HH:mm:ss"
            value-format="YYYY-MM-DDTHH:mm:ss"
            style="width: 360px"
          />
        </el-form-item>
        <el-form-item label="通道">
          <el-select
            v-model="queryForm.channel_ids"
            multiple
            collapse-tags
            placeholder="不限"
            style="width: 180px"
          >
            <el-option
              v-for="c in channels"
              :key="c.id"
              :label="c.name || c.channel_name"
              :value="c.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <el-form :model="queryForm" inline>
        <el-form-item label="自动抽样">
          <el-switch v-model="queryForm.sampling" active-text="开启" />
        </el-form-item>
        <el-form-item v-if="queryForm.sampling" label="最大点数">
          <el-input-number
            v-model="queryForm.max_points"
            :min="100"
            :max="50000"
            :step="100"
            style="width: 140px"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="doQuery" :loading="loading">
            <el-icon><Search /></el-icon>查询
          </el-button>
          <el-button @click="resetQuery">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="result-card" shadow="never">
      <template #header>
        <span>查询结果</span>
        <span class="result-count" v-if="pagination.total > 0">
          共 {{ pagination.total }} 条记录
        </span>
        <el-button
          type="warning"
          size="small"
          class="replay-btn"
          :disabled="!pagination.total"
          @click="openReplay"
        >▶ 回放</el-button>
      </template>
      <el-table
        :data="tableData"
        v-loading="loading"
        stripe
        size="small"
        max-height="calc(100vh - 500px)"
      >
        <el-table-column label="时间" width="180">
          <template #default="{ row }">
            {{ row.ts ? dayjs(row.ts).format('YYYY-MM-DD HH:mm:ss') : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="param_code" label="参数代号" width="150" show-overflow-tooltip />
        <el-table-column label="原始值" width="140">
          <template #default="{ row }">{{ row.raw_value ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="工程值" width="140">
          <template #default="{ row }">{{ row.value ?? '-' }}</template>
        </el-table-column>
        <el-table-column prop="quality" label="质量" width="90">
          <template #default="{ row }">
            <el-tag :type="qualityTagType(row.quality)" size="small">
              {{ row.quality || '-' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.page_size"
          :page-sizes="[20, 50, 100, 200]"
          :total="pagination.total"
          layout="total, sizes, prev, pager, next, jumper"
          background
          @size-change="doQuery"
          @current-change="doQuery"
        />
      </div>
    </el-card>

    <!-- 历史数据回放抽屉 -->
    <el-drawer
      v-model="replayVisible"
      title="历史数据回放"
      size="72%"
      direction="rtl"
      destroy-on-close
      @closed="destroyReplayChart"
    >
      <div v-loading="replayLoading" class="replay-body">
        <el-empty v-if="!replayLoading && replayPoints.length === 0" description="该时间范围内无数据可回放" />
        <template v-else>
          <div ref="replayChartEl" class="replay-chart"></div>
          <div class="replay-controls">
            <el-button-group>
              <el-button
                size="small"
                :type="replayPlaying ? 'warning' : 'primary'"
                :disabled="replayPoints.length === 0"
                @click="togglePlay"
              >{{ replayPlaying ? '暂停' : '播放' }}</el-button>
              <el-button size="small" :disabled="replayPoints.length === 0" @click="restartReplay">重播</el-button>
            </el-button-group>
            <div class="replay-progress">
              <span class="time-label">{{ replayCurrentTime }}</span>
              <el-slider
                v-model="replayIndex"
                :max="replayMax"
                :show-tooltip="false"
                :disabled="replayPoints.length === 0"
                style="flex: 1; margin: 0 12px"
                @input="onSeek"
              />
              <span class="time-label">{{ replayTotalTime }}</span>
            </div>
            <el-select v-model="replaySpeed" size="small" style="width: 90px" @change="onSpeedChange">
              <el-option label="1x" :value="1" />
              <el-option label="2x" :value="2" />
              <el-option label="4x" :value="4" />
            </el-select>
            <span class="replay-count">{{ replayIndex + 1 }} / {{ replayPoints.length }}</span>
          </div>
          <div class="replay-values">
            <el-table :data="replayValueRows" size="small" stripe max-height="220">
              <el-table-column prop="param_code" label="参数代号" width="150" />
              <el-table-column label="当前工程值" width="130">
                <template #default="{ row }">{{ row.value ?? '-' }}</template>
              </el-table-column>
              <el-table-column label="源码" width="130">
                <template #default="{ row }">{{ row.raw_value ?? '-' }}</template>
              </el-table-column>
              <el-table-column prop="unit" label="单位" width="90" />
            </el-table>
          </div>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import * as echarts from 'echarts'
import { telemetryApi } from '../api/telemetry'
import { satelliteApi, paramApi, channelApi } from '../api/satellite'

const satellites = ref([])
const paramOptions = ref([])
const channels = ref([])
const tableData = ref([])
const loading = ref(false)

const queryForm = reactive({
  satellite_id: null,
  param_codes: [],
  timeRange: null,
  channel_ids: [],
  sampling: false,
  max_points: 1000
})

const pagination = reactive({
  page: 1,
  page_size: 50,
  total: 0
})

// ---- 回放状态 ----
const replayVisible = ref(false)
const replayLoading = ref(false)
const replayPoints = ref([])          // 全量点（按时间升序，含 tsMs）
const replayIndex = ref(0)            // 当前播放到的点下标
const replayPlaying = ref(false)
const replaySpeed = ref(1)            // 1 / 2 / 4
const replayChartEl = ref(null)
const replayCurrentTime = ref('--:--:--')
const replayCurrentValues = ref({})   // code -> {value, raw_value, unit}
let replayChart = null
let replayTimer = null

const replayMax = computed(() => Math.max(0, replayPoints.value.length - 1))
const replayTotalTime = computed(() => {
  const pts = replayPoints.value
  if (!pts.length) return '--:--:--'
  return dayjs(pts[pts.length - 1].tsMs).format('HH:mm:ss')
})
const replayValueRows = computed(() => {
  return Object.keys(replayCurrentValues.value).map((code) => ({
    param_code: code,
    value: replayCurrentValues.value[code]?.value,
    raw_value: replayCurrentValues.value[code]?.raw_value,
    unit: replayCurrentValues.value[code]?.unit || ''
  }))
})

function qualityTagType(quality) {
  if (!quality) return 'info'
  const q = String(quality).toLowerCase()
  if (q === 'good' || q === 'valid' || q === '正常') return 'success'
  if (q === 'warning' || q === 'caution') return 'warning'
  if (q === 'bad' || q === 'invalid' || q === '异常') return 'danger'
  return 'info'
}

async function loadSatellites() {
  try {
    const res = await satelliteApi.list()
    satellites.value = Array.isArray(res) ? res : (res.items || res.data || [])
  } catch {
    satellites.value = []
  }
}

async function loadParams(satelliteId) {
  if (!satelliteId) {
    paramOptions.value = []
    return
  }
  try {
    const res = await paramApi.list({ satellite_id: satelliteId })
    const list = Array.isArray(res) ? res : (res.items || res.data || [])
    paramOptions.value = list.map((p) => ({
      code: p.code || p.param_code,
      name: p.name || p.code || p.param_code
    }))
  } catch {
    paramOptions.value = []
  }
}

async function loadChannels(satelliteId) {
  if (!satelliteId) {
    channels.value = []
    return
  }
  try {
    const res = await channelApi.list({ satellite_id: satelliteId })
    channels.value = Array.isArray(res) ? res : (res.items || res.data || [])
  } catch {
    channels.value = []
  }
}

function onSatelliteChange(val) {
  queryForm.param_codes = []
  queryForm.channel_ids = []
  loadParams(val)
  loadChannels(val)
}

function buildQueryParams() {
  const params = {
    page: pagination.page,
    page_size: pagination.page_size
  }

  if (queryForm.satellite_id) {
    params.satellite_id = queryForm.satellite_id
  }
  if (queryForm.param_codes && queryForm.param_codes.length > 0) {
    params.param_codes = queryForm.param_codes.join(',')
  }
  if (queryForm.timeRange && queryForm.timeRange.length === 2) {
    params.start = queryForm.timeRange[0]
    params.end = queryForm.timeRange[1]
  }
  if (queryForm.channel_ids && queryForm.channel_ids.length > 0) {
    params.channel_ids = queryForm.channel_ids.join(',')
  }
  if (queryForm.sampling) {
    params.sampling = 'auto'
    if (queryForm.max_points) {
      params.max_points = queryForm.max_points
    }
  }

  return params
}

async function doQuery() {
  if (!queryForm.satellite_id) {
    ElMessage.warning('请选择卫星')
    return
  }
  if (!queryForm.param_codes || queryForm.param_codes.length === 0) {
    ElMessage.warning('请至少选择一个参数')
    return
  }

  loading.value = true
  try {
    const params = buildQueryParams()
    const res = await telemetryApi.query(params)
    tableData.value = Array.isArray(res.points) ? res.points : (res.items || res.data || [])
    pagination.total = res.total || 0
  } catch {
    tableData.value = []
    pagination.total = 0
  } finally {
    loading.value = false
  }
}

function resetQuery() {
  queryForm.satellite_id = null
  queryForm.param_codes = []
  queryForm.timeRange = null
  queryForm.channel_ids = []
  queryForm.sampling = false
  queryForm.max_points = 1000
  pagination.page = 1
  pagination.page_size = 50
  pagination.total = 0
  tableData.value = []
  paramOptions.value = []
  channels.value = []
}

// ===================================================================
// 历史数据回放
// ===================================================================
async function openReplay() {
  if (!queryForm.param_codes || queryForm.param_codes.length === 0) {
    ElMessage.warning('请先选择参数')
    return
  }
  if (!queryForm.timeRange || queryForm.timeRange.length !== 2) {
    ElMessage.warning('请选择时间范围')
    return
  }
  replayVisible.value = true
  replayLoading.value = true
  pauseReplay()
  replayPoints.value = []
  replayIndex.value = 0
  replayCurrentValues.value = {}
  replayCurrentTime.value = '--:--:--'
  try {
    // 回放使用自动抽样全量数据（最多 2000 点），一次拉取后本地播放
    const params = buildQueryParams()
    params.sampling = 'auto'
    params.max_points = 2000
    const res = await telemetryApi.query(params)
    const pts = Array.isArray(res.points) ? res.points : []
    replayPoints.value = pts
      .map((p) => ({ ...p, tsMs: new Date(p.ts).getTime() }))
      .sort((a, b) => a.tsMs - b.tsMs)
    if (replayPoints.value.length === 0) {
      ElMessage.info('该时间范围内无数据可回放')
      return
    }
    await nextTick()
    initReplayChart()
    renderReplayFrame()
    playReplay()
  } catch {
    ElMessage.error('回放数据加载失败')
  } finally {
    replayLoading.value = false
  }
}

function initReplayChart() {
  if (!replayChartEl.value) return
  if (replayChart) {
    replayChart.dispose()
  }
  replayChart = echarts.init(replayChartEl.value)
  replayChart.setOption({
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v) => (v == null ? '-' : Number(v).toFixed(2))
    },
    grid: { left: 50, right: 20, top: 40, bottom: 40 },
    legend: { data: [], textStyle: { color: '#666' } },
    xAxis: {
      type: 'time',
      axisLabel: { formatter: (v) => dayjs(v).format('HH:mm:ss') }
    },
    yAxis: { type: 'value', scale: true },
    series: []
  })
}

function renderReplayFrame() {
  if (!replayChart) return
  const sliced = replayPoints.value.slice(0, replayIndex.value + 1)
  const byParam = {}
  const current = {}
  sliced.forEach((p) => {
    if (!byParam[p.param_code]) byParam[p.param_code] = []
    byParam[p.param_code].push([p.tsMs, p.value])
    current[p.param_code] = {
      value: p.value,
      raw_value: p.raw_value,
      unit: p.unit || ''
    }
  })
  const codes = Object.keys(byParam)
  replayChart.setOption({
    legend: { data: codes },
    series: codes.map((code) => ({
      name: code,
      type: 'line',
      showSymbol: false,
      connectNulls: true,
      lineStyle: { width: 2 },
      data: byParam[code]
    }))
  })
  replayCurrentValues.value = current
  const cur = replayPoints.value[replayIndex.value]
  replayCurrentTime.value = cur ? dayjs(cur.tsMs).format('HH:mm:ss') : '--:--:--'
}

function playReplay() {
  if (replayPlaying.value || replayPoints.value.length === 0) return
  replayPlaying.value = true
  replayTimer = setInterval(() => {
    const next = replayIndex.value + replaySpeed.value
    if (next >= replayPoints.value.length - 1) {
      replayIndex.value = replayPoints.value.length - 1
      renderReplayFrame()
      pauseReplay()
      return
    }
    replayIndex.value = next
    renderReplayFrame()
  }, 200)
}

function pauseReplay() {
  replayPlaying.value = false
  if (replayTimer) {
    clearInterval(replayTimer)
    replayTimer = null
  }
}

function togglePlay() {
  if (replayPlaying.value) {
    pauseReplay()
  } else {
    if (replayIndex.value >= replayMax.value) {
      replayIndex.value = 0
    }
    playReplay()
  }
}

function restartReplay() {
  pauseReplay()
  replayIndex.value = 0
  renderReplayFrame()
  playReplay()
}

function onSeek() {
  // 拖动进度条时暂停并跳转到对应帧
  pauseReplay()
  renderReplayFrame()
}

function onSpeedChange() {
  if (!replayPlaying.value) return
  // 速度切换：重启定时器生效
  pauseReplay()
  playReplay()
}

function destroyReplayChart() {
  pauseReplay()
  if (replayChart) {
    replayChart.dispose()
    replayChart = null
  }
}

onMounted(() => {
  loadSatellites()
})

onBeforeUnmount(() => {
  destroyReplayChart()
})
</script>

<style scoped>
.history-page {
}

.page-title {
  margin: 0 0 16px;
  font-size: 20px;
  color: #1a1a2e;
}

.query-card {
  margin-bottom: 16px;
}

.query-card :deep(.el-card__body) {
  padding-bottom: 4px;
}

.result-card {
  margin-bottom: 16px;
}

.result-count {
  font-size: 13px;
  color: #999;
  margin-left: 12px;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.replay-btn {
  margin-left: 12px;
}

.replay-body {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.replay-chart {
  flex: 1;
  min-height: 360px;
  width: 100%;
}

.replay-controls {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 14px 0;
  padding: 10px 12px;
  background: #f8f9fb;
  border-radius: 6px;
}

.replay-progress {
  flex: 1;
  display: flex;
  align-items: center;
}

.time-label {
  font-size: 12px;
  color: #666;
  font-variant-numeric: tabular-nums;
  min-width: 70px;
  text-align: center;
}

.replay-count {
  font-size: 12px;
  color: #999;
  font-variant-numeric: tabular-nums;
  min-width: 70px;
  text-align: right;
}
</style>
