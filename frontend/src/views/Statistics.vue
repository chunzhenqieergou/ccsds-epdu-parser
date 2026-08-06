<template>
  <div class="statistics-page">
    <div class="page-header">
      <h3 class="page-title">统计分析</h3>
      <p class="page-desc">基础统计 / 趋势分析 / 异常检测 / 阶段对比</p>
    </div>

    <el-card shadow="never" class="filter-card">
      <el-form :inline="true" size="default">
        <el-form-item label="参数">
          <el-select
            v-model="selectedParam"
            filterable
            placeholder="请选择遥测参数"
            @change="onParamChange"
            style="width: 220px"
          >
            <el-option
              v-for="p in paramList"
              :key="p.id"
              :label="p.param_code + ' (' + (p.param_name || p.param_code) + ')'"
              :value="p.param_code"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="timeRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始"
            end-placeholder="结束"
            value-format="YYYY-MM-DD HH:mm:ss"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="doStatistics" :loading="loading">统计分析</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-row :gutter="20" style="margin-top: 16px" v-if="basicStats">
      <el-col :span="24">
        <el-card shadow="never">
          <template #header><span>基本统计量</span></template>
          <el-row :gutter="16">
            <el-col :xs="12" :sm="8" :md="4" v-for="item in statsCards" :key="item.label">
              <div class="mini-stat">
                <div class="mini-stat-label">{{ item.label }}</div>
                <div class="mini-stat-value">{{ item.value }}</div>
              </div>
            </el-col>
          </el-row>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 16px">
      <el-col :span="12" v-if="trendResult">
        <el-card shadow="never">
          <template #header><span>趋势分析</span></template>
          <div class="trend-display">
            <span class="trend-icon">{{ trendIcon }}</span>
            <div>
              <div class="trend-label">参数: {{ trendResult.param_code }}</div>
              <div class="trend-desc">趋势方向: {{ trendDirectionText }}</div>
              <div v-if="trendResult.change_rate !== undefined" class="trend-desc">
                变化率: {{ (trendResult.change_rate * 100).toFixed(2) }}%
              </div>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="12" v-if="anomalyData && anomalyData.length">
        <el-card shadow="never">
          <template #header><span>异常检测</span></template>
          <el-table :data="anomalyData" size="small" max-height="300">
            <el-table-column prop="param_code" label="参数" width="120" />
            <el-table-column prop="value" label="数值" width="100" />
            <el-table-column prop="threshold" label="阈值" width="100" />
            <el-table-column prop="timestamp" label="时间" width="160">
              <template #default="{ row }">
                {{ formatTime(row.timestamp || row.time) }}
              </template>
            </el-table-column>
            <el-table-column prop="description" label="描述" min-width="160" show-overflow-tooltip />
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 16px" v-if="compareResult">
      <el-col :span="24">
        <el-card shadow="never">
          <template #header><span>阶段对比 ({{ compareResult.param_code }})</span></template>
          <el-table :data="compareTableData" size="small">
            <el-table-column prop="metric" label="指标" width="120" />
            <el-table-column prop="period1" label="时段1" />
            <el-table-column prop="period2" label="时段2" />
            <el-table-column prop="delta" label="差值">
              <template #default="{ row }">
                <span :style="{ color: row.delta > 0 ? '#f56c6c' : row.delta < 0 ? '#67c23a' : '#909399' }">
                  {{ row.delta }}
                </span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 16px">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header><span>阶段对比设置</span></template>
          <el-form size="default">
            <el-form-item label="参数">
              <el-select v-model="compareParam" filterable placeholder="选择参数" style="width: 200px">
                <el-option v-for="p in paramList" :key="p.id" :label="p.param_code" :value="p.param_code" />
              </el-select>
            </el-form-item>
            <el-form-item label="时段1">
              <el-date-picker
                v-model="compareTime1"
                type="datetimerange"
                range-separator="至"
                start-placeholder="开始"
                end-placeholder="结束"
                value-format="YYYY-MM-DD HH:mm:ss"
              />
            </el-form-item>
            <el-form-item label="时段2">
              <el-date-picker
                v-model="compareTime2"
                type="datetimerange"
                range-separator="至"
                start-placeholder="开始"
                end-placeholder="结束"
                value-format="YYYY-MM-DD HH:mm:ss"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="doCompare" :loading="compareLoading">对比分析</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import { paramApi } from '../api/satellite'
import { statisticsApi } from '../api/telemetry'

const paramList = ref([])
const selectedParam = ref('')
const timeRange = ref([])
const loading = ref(false)

const basicStats = ref(null)
const trendResult = ref(null)
const anomalyData = ref([])
const compareResult = ref(null)

const compareParam = ref('')
const compareTime1 = ref([])
const compareTime2 = ref([])
const compareLoading = ref(false)

const statsCards = computed(() => {
  if (!basicStats.value) return []
  const s = basicStats.value
  return [
    { label: '样本数', value: s.count ?? '-' },
    { label: '最小值', value: s.min != null ? Number(s.min).toFixed(4) : '-' },
    { label: '最大值', value: s.max != null ? Number(s.max).toFixed(4) : '-' },
    { label: '均值', value: s.mean != null ? Number(s.mean).toFixed(4) : '-' },
    { label: '方差', value: s.variance != null ? Number(s.variance).toFixed(4) : '-' },
    { label: '标准差', value: s.std != null ? Number(s.std).toFixed(4) : '-' }
  ]
})

const trendIcon = computed(() => {
  if (!trendResult.value) return '—'
  const d = trendResult.value.direction || trendResult.value.trend || ''
  if (d === 'up' || d === 'increase' || d === 'rising') return '↑'
  if (d === 'down' || d === 'decrease' || d === 'falling') return '↓'
  return '↔'
})

const trendDirectionText = computed(() => {
  if (!trendResult.value) return ''
  const d = trendResult.value.direction || trendResult.value.trend || ''
  const map = { up: '上升', increase: '上升', rising: '上升', down: '下降', decrease: '下降', falling: '下降', stable: '平稳' }
  return map[d] || d || '平稳'
})

const compareTableData = computed(() => {
  if (!compareResult.value) return []
  const r = compareResult.value
  return [
    { metric: '均值', period1: r.period1?.mean?.toFixed?.(4) ?? '-', period2: r.period2?.mean?.toFixed?.(4) ?? '-', delta: r.delta?.mean?.toFixed?.(4) ?? '-' },
    { metric: '最大值', period1: r.period1?.max?.toFixed?.(4) ?? '-', period2: r.period2?.max?.toFixed?.(4) ?? '-', delta: r.delta?.max?.toFixed?.(4) ?? '-' },
    { metric: '最小值', period1: r.period1?.min?.toFixed?.(4) ?? '-', period2: r.period2?.min?.toFixed?.(4) ?? '-', delta: r.delta?.min?.toFixed?.(4) ?? '-' },
    { metric: '方差', period1: r.period1?.variance?.toFixed?.(4) ?? '-', period2: r.period2?.variance?.toFixed?.(4) ?? '-', delta: r.delta?.variance?.toFixed?.(4) ?? '-' }
  ]
})

function formatTime(t) {
  return t ? dayjs(t).format('YYYY-MM-DD HH:mm:ss') : '-'
}

async function fetchParams() {
  try {
    const data = await paramApi.list({ limit: 200 })
    paramList.value = Array.isArray(data) ? data : (data.items || [])
  } catch {}
}

function onParamChange() {
  basicStats.value = null
  trendResult.value = null
  anomalyData.value = []
}

async function doStatistics() {
  if (!selectedParam.value) { ElMessage.warning('请选择参数'); return }
  if (!timeRange.value?.length) { ElMessage.warning('请选择时间范围'); return }
  const [start, end] = timeRange.value
  const params = { param_code: selectedParam.value, start, end }
  loading.value = true
  try {
    const [basic, trend, anomaly] = await Promise.allSettled([
      statisticsApi.basic(params),
      statisticsApi.trend(params),
      statisticsApi.anomaly(params)
    ])
    if (basic.status === 'fulfilled') basicStats.value = basic.value
    if (trend.status === 'fulfilled') trendResult.value = trend.value
    if (anomaly.status === 'fulfilled') {
      const d = anomaly.value
      anomalyData.value = Array.isArray(d) ? d : (d.items || d.anomalies || [])
    }
  } catch {} finally {
    loading.value = false
  }
}

async function doCompare() {
  if (!compareParam.value || !compareTime1.value?.length || !compareTime2.value?.length) {
    ElMessage.warning('请填写完整的对比参数')
    return
  }
  compareLoading.value = true
  try {
    const [s1, e1] = compareTime1.value
    const [s2, e2] = compareTime2.value
    const result = await statisticsApi.compare({
      param_code: compareParam.value,
      period1_start: s1,
      period1_end: e1,
      period2_start: s2,
      period2_end: e2
    })
    compareResult.value = result
  } catch {} finally {
    compareLoading.value = false
  }
}

fetchParams()
</script>

<style scoped>
.statistics-page { }
.page-header { margin-bottom: 16px; }
.page-title { margin: 0 0 4px; font-size: 20px; color: #1a1a2e; }
.page-desc { margin: 0; color: #999; font-size: 14px; }
.filter-card { margin-bottom: 0; }
.mini-stat { text-align: center; padding: 12px 8px; background: #fafafa; border-radius: 6px; }
.mini-stat-label { font-size: 13px; color: #999; margin-bottom: 6px; }
.mini-stat-value { font-size: 22px; font-weight: 700; color: #1a1a2e; }
.trend-display { display: flex; align-items: center; gap: 20px; padding: 8px 0; }
.trend-icon { font-size: 48px; line-height: 1; }
.trend-label { font-size: 16px; font-weight: 600; color: #1a1a2e; margin-bottom: 4px; }
.trend-desc { font-size: 14px; color: #666; margin-top: 2px; }
</style>
