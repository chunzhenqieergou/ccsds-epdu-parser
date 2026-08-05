<template>
  <div class="satellite-list">
    <div class="page-header">
      <h3 class="page-title">卫星管理</h3>
      <p class="page-desc">管理卫星基本信息，支持新增、编辑和删除操作</p>
    </div>

    <div class="toolbar">
      <div class="toolbar-left">
        <el-input
          v-model="keyword"
          placeholder="搜索卫星名称或代号"
          clearable
          style="width: 280px"
          @keyup.enter="handleSearch"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-button type="primary" @click="handleSearch">
          <el-icon><Search /></el-icon>
          搜索
        </el-button>
      </div>
      <div class="toolbar-right">
        <el-button v-if="canEdit" type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>
          新增卫星
        </el-button>
      </div>
    </div>

    <el-table :data="tableData" v-loading="loading" border stripe>
      <el-table-column prop="name" label="卫星名称" min-width="140" />
      <el-table-column prop="code" label="卫星代号" min-width="120" />
      <el-table-column prop="orbit_type" label="轨道类型" min-width="110">
        <template #default="{ row }">
          <el-tag size="small">{{ row.orbit_type || '-' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="launch_date" label="发射日期" min-width="120">
        <template #default="{ row }">
          {{ row.launch_date || '-' }}
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" min-width="100">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small">
            {{ statusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="param_count" label="参数数" width="90" align="center" />
      <el-table-column prop="created_at" label="创建时间" min-width="160" />
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
      width="560px"
      :close-on-click-modal="false"
      @closed="handleDialogClosed"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="卫星名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入卫星名称" maxlength="64" />
        </el-form-item>
        <el-form-item label="卫星代号" prop="code">
          <el-input v-model="form.code" placeholder="请输入卫星代号" maxlength="32" />
        </el-form-item>
        <el-form-item label="轨道类型" prop="orbit_type">
          <el-select v-model="form.orbit_type" placeholder="请选择轨道类型" style="width: 100%">
            <el-option v-for="o in orbitTypes" :key="o" :label="o" :value="o" />
          </el-select>
        </el-form-item>
        <el-form-item label="发射日期">
          <el-date-picker
            v-model="form.launch_date"
            type="date"
            placeholder="请选择发射日期"
            style="width: 100%"
            value-format="YYYY-MM-DD"
          />
        </el-form-item>
        <el-form-item label="状态" prop="status">
          <el-select v-model="form.status" placeholder="请选择状态" style="width: 100%">
            <el-option label="服役中" value="active" />
            <el-option label="备用" value="standby" />
            <el-option label="退役" value="retired" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            placeholder="请输入描述信息"
            maxlength="256"
          />
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
import { Search, Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '../../stores/auth'
import { satelliteApi } from '../../api/satellite'

const authStore = useAuthStore()
const { role } = storeToRefs(authStore)
const canEdit = computed(() => role.value === 'admin' || role.value === 'operator')

const orbitTypes = ['LEO', 'MEO', 'GEO', 'HEO', 'SSO', 'IGSO']

const loading = ref(false)
const keyword = ref('')
const tableData = ref([])
const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

const dialogVisible = ref(false)
const dialogTitle = ref('新增卫星')
const editId = ref(null)
const submitLoading = ref(false)
const formRef = ref(null)

const defaultForm = () => ({
  name: '',
  code: '',
  orbit_type: '',
  launch_date: '',
  status: 'active',
  description: ''
})
const form = reactive(defaultForm())

const rules = {
  name: [{ required: true, message: '请输入卫星名称', trigger: 'blur' }],
  code: [{ required: true, message: '请输入卫星代号', trigger: 'blur' }],
  orbit_type: [{ required: true, message: '请选择轨道类型', trigger: 'change' }],
  status: [{ required: true, message: '请选择状态', trigger: 'change' }]
}

function statusTagType(status) {
  const map = { active: 'success', standby: 'warning', retired: 'info' }
  return map[status] || 'info'
}

function statusLabel(status) {
  const map = { active: '服役中', standby: '备用', retired: '退役' }
  return map[status] || status || '-'
}

async function fetchData() {
  loading.value = true
  try {
    const res = await satelliteApi.list({
      page: pagination.page,
      page_size: pagination.pageSize,
      keyword: keyword.value
    })
    tableData.value = res.items || []
    pagination.total = res.total || 0
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  pagination.page = 1
  fetchData()
}

function handleSizeChange() {
  pagination.page = 1
  fetchData()
}

function openCreate() {
  editId.value = null
  dialogTitle.value = '新增卫星'
  Object.assign(form, defaultForm())
  dialogVisible.value = true
}

function openEdit(row) {
  editId.value = row.id
  dialogTitle.value = '编辑卫星'
  Object.assign(form, {
    name: row.name || '',
    code: row.code || '',
    orbit_type: row.orbit_type || '',
    launch_date: row.launch_date || '',
    status: row.status || 'active',
    description: row.description || ''
  })
  dialogVisible.value = true
}

async function handleSubmit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  submitLoading.value = true
  try {
    const payload = {
      name: form.name,
      code: form.code,
      orbit_type: form.orbit_type,
      launch_date: form.launch_date || null,
      status: form.status,
      description: form.description
    }
    if (editId.value) {
      await satelliteApi.update(editId.value, payload)
      ElMessage.success('卫星更新成功')
    } else {
      await satelliteApi.create(payload)
      ElMessage.success('卫星创建成功')
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
      `确认删除卫星「${row.name}」？删除后不可恢复。`,
      '删除确认',
      { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await satelliteApi.remove(row.id)
    ElMessage.success('卫星已删除')
    fetchData()
  } catch { /* 全局拦截已提示 */ }
}

function handleDialogClosed() {
  formRef.value?.resetFields()
}

onMounted(() => {
  fetchData()
})
</script>

<style scoped>
.satellite-list {
  max-width: 1400px;
}

.page-header { margin-bottom: 16px; }
.page-title { margin: 0 0 4px; font-size: 20px; color: #1a1a2e; }
.page-desc { margin: 0; color: #999; font-size: 14px; }

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.pagination-wrap {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
