<template>
  <div class="logs-page">
    <div class="page-header">
      <h3 class="page-title">操作日志</h3>
      <p class="page-desc">系统操作日志审计</p>
    </div>

    <el-card shadow="never" class="filter-card">
      <el-form :inline="true" size="default">
        <el-form-item label="操作类型">
          <el-input v-model="filterAction" placeholder="输入操作类型" style="width: 200px" clearable @clear="fetchLogs" />
        </el-form-item>
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="filterTimeRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始"
            end-placeholder="结束"
            value-format="YYYY-MM-DD HH:mm:ss"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="fetchLogs" :loading="loading">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" style="margin-top: 16px">
      <el-table :data="logs" v-loading="loading" stripe size="default">
        <el-table-column type="index" label="#" width="60" />
        <el-table-column prop="action" label="操作类型" width="140">
          <template #default="{ row }">
            <el-tag size="small">{{ row.action || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="username" label="操作用户" width="140" />
        <el-table-column prop="resource" label="资源" width="160" show-overflow-tooltip />
        <el-table-column prop="ip_address" label="IP地址" width="150">
          <template #default="{ row }">{{ row.ip_address || row.ip || '-' }}</template>
        </el-table-column>
        <el-table-column label="时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.created_at || row.timestamp || row.time) }}
          </template>
        </el-table-column>
        <el-table-column prop="detail" label="详情" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.detail || row.message || row.description || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : row.status === 'failure' ? 'danger' : 'info'" size="small">
              {{ row.status || '-' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>

      <div style="margin-top: 16px; text-align: right">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @current-change="fetchLogs"
          @size-change="fetchLogs"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import dayjs from 'dayjs'
import { logApi } from '../../api/system'

const loading = ref(false)
const logs = ref([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const filterAction = ref('')
const filterTimeRange = ref([])

function formatTime(t) {
  return t ? dayjs(t).format('YYYY-MM-DD HH:mm:ss') : '-'
}

async function fetchLogs() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (filterAction.value) params.action = filterAction.value
    if (filterTimeRange.value?.length) {
      params.start = filterTimeRange.value[0]
      params.end = filterTimeRange.value[1]
    }
    const data = await logApi.list(params)
    if (Array.isArray(data)) {
      logs.value = data
      total.value = data.length
    } else {
      logs.value = data.items || data.logs || []
      total.value = data.total || data.count || logs.value.length
    }
  } catch {} finally {
    loading.value = false
  }
}

function resetFilters() {
  filterAction.value = ''
  filterTimeRange.value = []
  page.value = 1
  fetchLogs()
}

onMounted(fetchLogs)
</script>

<style scoped>
.logs-page { max-width: 1400px; }
.page-header { margin-bottom: 16px; }
.page-title { margin: 0 0 4px; font-size: 20px; color: #1a1a2e; }
.page-desc { margin: 0; color: #999; font-size: 14px; }
.filter-card { margin-bottom: 0; }
</style>
