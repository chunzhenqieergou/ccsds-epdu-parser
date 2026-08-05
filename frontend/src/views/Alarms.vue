<template>
  <div class="alarms-page">
    <div class="page-header">
      <h3 class="page-title">告警中心</h3>
      <p class="page-desc">遥测告警监控与处理</p>
    </div>

    <el-card shadow="never" class="filter-card">
      <el-form :inline="true" size="default">
        <el-form-item label="级别">
          <el-select v-model="filterLevel" placeholder="全部级别" clearable style="width: 140px" @change="fetchAlarms">
            <el-option label="Info" value="Info" />
            <el-option label="Warn" value="Warn" />
            <el-option label="Critical" value="Critical" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filterStatus" placeholder="全部状态" clearable style="width: 140px" @change="fetchAlarms">
            <el-option label="未处理" value="pending" />
            <el-option label="已处理" value="handled" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="fetchAlarms" :loading="loading">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" style="margin-top: 16px">
      <el-table :data="sortedAlarms" v-loading="loading" size="default" stripe>
        <el-table-column label="级别" width="100">
          <template #default="{ row }">
            <el-tag
              :type="row.level === 'Critical' ? 'danger' : row.level === 'Warn' ? 'warning' : 'info'"
              size="small"
            >
              {{ row.level || 'Info' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="param_code" label="参数" width="140" show-overflow-tooltip />
        <el-table-column prop="value" label="触发值" width="100" />
        <el-table-column prop="threshold" label="阈值" width="100" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'handled' ? 'success' : 'danger'" size="small">
              {{ row.status === 'handled' ? '已处理' : '未处理' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.created_at || row.timestamp || row.time) }}
          </template>
        </el-table-column>
        <el-table-column prop="message" label="描述" min-width="160" show-overflow-tooltip />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status !== 'handled'"
              type="primary"
              size="small"
              @click="openHandleDialog(row)"
            >
              处理
            </el-button>
            <el-button type="danger" size="small" @click="deleteAlarm(row)">删除</el-button>
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
          @current-change="fetchAlarms"
          @size-change="fetchAlarms"
        />
      </div>
    </el-card>

    <el-dialog v-model="handleDialogVisible" title="处理告警" width="460px" :close-on-click-modal="false">
      <el-form :model="handleForm" label-width="80px" size="default">
        <el-form-item label="参数">
          <span>{{ currentAlarm?.param_code }}</span>
        </el-form-item>
        <el-form-item label="触发值">
          <span>{{ currentAlarm?.value }}</span>
        </el-form-item>
        <el-form-item label="处理备注" prop="remark">
          <el-input
            v-model="handleForm.remark"
            type="textarea"
            :rows="3"
            placeholder="请输入处理备注"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="handleDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="handleLoading" @click="doHandle">确认处理</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'
import { alarmApi } from '../api/telemetry'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()

const loading = ref(false)
const alarms = ref([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const filterLevel = ref('')
const filterStatus = ref('')

const handleDialogVisible = ref(false)
const currentAlarm = ref(null)
const handleLoading = ref(false)
const handleForm = reactive({ remark: '' })

const sortedAlarms = computed(() => {
  const list = [...alarms.value]
  list.sort((a, b) => {
    if ((a.status !== 'handled') && (b.status === 'handled')) return -1
    if ((a.status === 'handled') && (b.status !== 'handled')) return 1
    return 0
  })
  return list
})

function formatTime(t) {
  return t ? dayjs(t).format('YYYY-MM-DD HH:mm:ss') : '-'
}

async function fetchAlarms() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (filterLevel.value) params.level = filterLevel.value
    if (filterStatus.value) params.status = filterStatus.value
    const data = await alarmApi.list(params)
    if (Array.isArray(data)) {
      alarms.value = data
      total.value = data.length
    } else {
      alarms.value = data.items || data.records || data.alarms || []
      total.value = data.total || data.count || alarms.value.length
    }
  } catch {} finally {
    loading.value = false
  }
}

function resetFilters() {
  filterLevel.value = ''
  filterStatus.value = ''
  page.value = 1
  fetchAlarms()
}

function openHandleDialog(row) {
  currentAlarm.value = row
  handleForm.remark = ''
  handleDialogVisible.value = true
}

async function doHandle() {
  if (!currentAlarm.value) return
  handleLoading.value = true
  try {
    await alarmApi.handle(currentAlarm.value.id, {
      remark: handleForm.remark,
      handler: auth.user?.username || 'unknown'
    })
    ElMessage.success('告警已处理')
    handleDialogVisible.value = false
    fetchAlarms()
  } catch {} finally {
    handleLoading.value = false
  }
}

async function deleteAlarm(row) {
  try {
    await ElMessageBox.confirm('确定要删除该告警记录吗？', '确认删除', {
      type: 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消'
    })
  } catch { return }
  try {
    await alarmApi.remove(row.id)
    ElMessage.success('已删除')
    fetchAlarms()
  } catch {}
}

onMounted(fetchAlarms)
</script>

<style scoped>
.alarms-page { max-width: 1400px; }
.page-header { margin-bottom: 16px; }
.page-title { margin: 0 0 4px; font-size: 20px; color: #1a1a2e; }
.page-desc { margin: 0; color: #999; font-size: 14px; }
.filter-card { margin-bottom: 0; }
</style>
