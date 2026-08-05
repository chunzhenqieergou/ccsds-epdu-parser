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
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
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

onMounted(() => {
  loadSatellites()
})
</script>

<style scoped>
.history-page {
  max-width: 1400px;
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
</style>
