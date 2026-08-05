<template>
  <div class="params-page">
    <div class="page-header">
      <h3 class="page-title">遥测参数管理</h3>
      <p class="page-desc">配置卫星遥测参数，支持增删改查及导入导出</p>
    </div>

    <div class="toolbar">
      <div class="toolbar-row">
        <el-select v-model="filter.subsystem" placeholder="分系统筛选" clearable style="width: 160px" @change="handleFilter">
          <el-option v-for="s in subsystems" :key="s" :label="s" :value="s" />
        </el-select>
        <el-select v-model="filter.satelliteId" placeholder="卫星筛选（可选）" clearable style="width: 200px" @change="handleFilter">
          <el-option
            v-for="s in satelliteList"
            :key="s.id"
            :label="s.name + ' (' + s.code + ')'"
            :value="s.id"
          />
        </el-select>
        <el-input
          v-model="filter.keyword"
          placeholder="搜索参数代号或名称"
          clearable
          style="width: 220px"
          @keyup.enter="handleFilter"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-button type="primary" @click="handleFilter">
          <el-icon><Search /></el-icon>
          搜索
        </el-button>
      </div>
      <div class="toolbar-row" style="margin-top: 8px">
        <el-button v-if="canEdit" type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>
          新增参数
        </el-button>
        <el-upload
          v-if="canEdit"
          :show-file-list="false"
          :http-request="handleImport"
          accept=".json"
          style="display: inline-block; margin-left: 8px"
        >
          <el-button type="success">
            <el-icon><Upload /></el-icon>
            导入
          </el-button>
        </el-upload>
        <el-button style="margin-left: 8px" @click="handleExport">
          <el-icon><Download /></el-icon>
          导出
        </el-button>
      </div>
    </div>

    <el-table :data="tableData" v-loading="loading" border stripe>
      <el-table-column prop="param_code" label="参数代号" min-width="130" />
      <el-table-column prop="name" label="参数名称" min-width="140" />
      <el-table-column prop="subsystem" label="分系统" min-width="120">
        <template #default="{ row }">
          <el-tag size="small">{{ row.subsystem || '-' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="data_type" label="数据类型" width="100" align="center">
        <template #default="{ row }">
          <el-tag size="small" type="info">{{ row.data_type || '-' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="unit" label="单位" width="80" align="center" />
      <el-table-column label="量程" min-width="130">
        <template #default="{ row }">
          <template v-if="row.window">
            {{ row.window.min ?? '-' }} ~ {{ row.window.max ?? '-' }}
          </template>
          <template v-else>-</template>
        </template>
      </el-table-column>
      <el-table-column label="阈值" min-width="130">
        <template #default="{ row }">
          {{ row.threshold_min ?? '-' }} ~ {{ row.threshold_max ?? '-' }}
        </template>
      </el-table-column>
      <el-table-column prop="enabled" label="状态" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
            {{ row.enabled ? '启用' : '禁用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column v-if="canEdit" label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link @click="openEdit(row)">编辑</el-button>
          <el-button type="danger" link @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-wrap">
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :total="pagination.total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        @current-change="fetchData"
        @size-change="handleSizeChange"
      />
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="600px"
      :close-on-click-modal="false"
      @closed="handleDialogClosed"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="所属卫星" prop="satellite_id">
          <el-select v-model="form.satellite_id" placeholder="请选择卫星" style="width: 100%">
            <el-option
              v-for="s in satelliteList"
              :key="s.id"
              :label="s.name + ' (' + s.code + ')'"
              :value="s.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="参数代号" prop="param_code">
          <el-input v-model="form.param_code" placeholder="请输入参数代号" maxlength="64" />
        </el-form-item>
        <el-form-item label="参数名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入参数名称" maxlength="128" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="分系统" prop="subsystem">
              <el-select v-model="form.subsystem" placeholder="请选择分系统" style="width: 100%" filterable allow-create>
                <el-option v-for="s in subsystems" :key="s" :label="s" :value="s" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="数据类型" prop="data_type">
              <el-select v-model="form.data_type" placeholder="请选择数据类型" style="width: 100%">
                <el-option v-for="t in dataTypes" :key="t" :label="t" :value="t" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="单位" prop="unit">
              <el-input v-model="form.unit" placeholder="如 V, A, ℃" maxlength="16" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="缩放系数" prop="scale">
              <el-input-number v-model="form.scale" :step="0.1" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="偏移量" prop="offset">
              <el-input-number v-model="form.offset" :step="0.1" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="精度" prop="precision">
              <el-input-number v-model="form.precision" :min="0" :max="10" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="阈值下限" prop="threshold_min">
              <el-input-number v-model="form.threshold_min" :step="0.1" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="阈值上限" prop="threshold_max">
              <el-input-number v-model="form.threshold_max" :step="0.1" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="启用状态">
          <el-switch v-model="form.enabled" active-text="启用" inactive-text="禁用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { Search, Plus, Upload, Download } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '../../stores/auth'
import { satelliteApi, paramApi } from '../../api/satellite'

const authStore = useAuthStore()
const { role } = storeToRefs(authStore)
const canEdit = computed(() => role.value === 'admin' || role.value === 'operator')

const subsystems = ['电源', '热控', '姿轨控', '测控', '数传', '结构', '推进', '综合电子']
const dataTypes = ['uint8', 'int16', 'float', 'uint32', 'enum', 'int32', 'uint16', 'float64']

const loading = ref(false)
const tableData = ref([])
const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

const filter = reactive({
  keyword: '',
  subsystem: '',
  satelliteId: null
})

const satelliteList = ref([])

const dialogVisible = ref(false)
const dialogTitle = ref('新增参数')
const editId = ref(null)
const submitLoading = ref(false)
const formRef = ref(null)

const defaultForm = () => ({
  satellite_id: null,
  param_code: '',
  name: '',
  subsystem: '',
  data_type: '',
  unit: '',
  scale: 1,
  offset: 0,
  precision: 2,
  threshold_min: null,
  threshold_max: null,
  enabled: true
})
const form = reactive(defaultForm())

const rules = {
  satellite_id: [{ required: true, message: '请选择卫星', trigger: 'change' }],
  param_code: [{ required: true, message: '请输入参数代号', trigger: 'blur' }],
  name: [{ required: true, message: '请输入参数名称', trigger: 'blur' }],
  subsystem: [{ required: true, message: '请选择分系统', trigger: 'change' }],
  data_type: [{ required: true, message: '请选择数据类型', trigger: 'change' }]
}

async function fetchSatellites() {
  const res = await satelliteApi.list({ page: 1, page_size: 1000 })
  satelliteList.value = res.items || []
}

async function fetchData() {
  loading.value = true
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.pageSize,
      keyword: filter.keyword || undefined,
      subsystem: filter.subsystem || undefined,
      satellite_id: filter.satelliteId || undefined
    }
    const res = await paramApi.list(params)
    tableData.value = res.items || []
    pagination.total = res.total || 0
  } finally {
    loading.value = false
  }
}

function handleFilter() {
  pagination.page = 1
  fetchData()
}

function handleSizeChange() {
  pagination.page = 1
  fetchData()
}

function openCreate() {
  editId.value = null
  dialogTitle.value = '新增参数'
  Object.assign(form, defaultForm())
  dialogVisible.value = true
}

function openEdit(row) {
  editId.value = row.id
  dialogTitle.value = '编辑参数'
  const win = row.window || {}
  Object.assign(form, {
    satellite_id: row.satellite_id ?? null,
    param_code: row.param_code || '',
    name: row.name || '',
    subsystem: row.subsystem || '',
    data_type: row.data_type || '',
    unit: row.unit || '',
    scale: row.scale ?? 1,
    offset: row.offset ?? 0,
    precision: row.precision ?? 2,
    threshold_min: row.threshold_min ?? null,
    threshold_max: row.threshold_max ?? null,
    enabled: row.enabled ?? true
  })
  if (win.min !== undefined) {
    form.threshold_min = win.min
  }
  if (win.max !== undefined) {
    form.threshold_max = win.max
  }
  dialogVisible.value = true
}

async function handleSubmit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  submitLoading.value = true
  try {
    const payload = {
      satellite_id: form.satellite_id,
      param_code: form.param_code,
      name: form.name,
      subsystem: form.subsystem,
      data_type: form.data_type,
      unit: form.unit || '',
      scale: form.scale,
      offset: form.offset,
      precision: form.precision,
      threshold_min: form.threshold_min,
      threshold_max: form.threshold_max,
      enabled: form.enabled
    }
    if (editId.value) {
      await paramApi.update(editId.value, payload)
      ElMessage.success('参数更新成功')
    } else {
      await paramApi.create(payload)
      ElMessage.success('参数创建成功')
    }
    dialogVisible.value = false
    fetchData()
  } finally {
    submitLoading.value = false
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确认删除参数「${row.name}」？删除后不可恢复。`,
      '删除确认',
      { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await paramApi.remove(row.id)
    ElMessage.success('参数已删除')
    fetchData()
  } catch { /* 全局拦截已提示 */ }
}

async function handleImport(opts) {
  const file = opts.file
  if (!file) return
  const targetId = filter.satelliteId || null
  if (!targetId) {
    ElMessage.warning('请先在筛选区选择目标卫星')
    return
  }
  try {
    await paramApi.importExcel(targetId, file)
    ElMessage.success('参数导入成功')
    fetchData()
  } catch { /* 全局拦截已提示 */ }
}

async function handleExport() {
  const targetId = filter.satelliteId || null
  if (!targetId) {
    ElMessage.warning('请先在筛选区选择目标卫星')
    return
  }
  try {
    const blob = await paramApi.exportExcel(targetId)
    const url = window.URL.createObjectURL(new Blob([blob]))
    const a = document.createElement('a')
    a.href = url
    a.download = `params_${targetId}_${Date.now()}.json`
    a.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success('参数导出成功')
  } catch { /* 全局拦截已提示 */ }
}

function handleDialogClosed() {
  formRef.value?.resetFields()
}

onMounted(() => {
  fetchSatellites()
  fetchData()
})
</script>

<style scoped>
.params-page {
  max-width: 1500px;
}

.page-header { margin-bottom: 16px; }
.page-title { margin: 0 0 4px; font-size: 20px; color: #1a1a2e; }
.page-desc { margin: 0; color: #999; font-size: 14px; }

.toolbar {
  margin-bottom: 16px;
}

.toolbar-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.pagination-wrap {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
