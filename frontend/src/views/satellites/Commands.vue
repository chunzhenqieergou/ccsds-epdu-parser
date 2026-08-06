<template>
  <div class="commands-page">
    <div class="page-header">
      <h3 class="page-title">遥控指令管理</h3>
      <p class="page-desc">管理卫星遥控指令，支持指令发送操作</p>
    </div>

    <div class="toolbar">
      <div class="toolbar-left">
        <el-input
          v-model="keyword"
          placeholder="搜索指令代号或名称"
          clearable
          style="width: 240px"
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
          新增指令
        </el-button>
      </div>
    </div>

    <el-table :data="tableData" v-loading="loading" border stripe>
      <el-table-column prop="cmd_code" label="指令代号" min-width="140">
        <template #default="{ row }">
          <code class="cmd-code">{{ row.cmd_code }}</code>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="指令名称" min-width="140" />
      <el-table-column prop="permission_level" label="权限等级" width="110" align="center">
        <template #default="{ row }">
          <el-tag :type="permissionTagType(row.permission_level)" size="small">
            {{ permissionLabel(row.permission_level) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="forbidden" label="是否禁止" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="row.forbidden ? 'danger' : 'success'" size="small">
            {{ row.forbidden ? '禁止' : '正常' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
      <el-table-column label="操作" width="210" fixed="right">
        <template #default="{ row }">
          <el-button v-if="canEdit" type="primary" link @click="openEdit(row)">编辑</el-button>
          <el-button v-if="canEdit" type="danger" link @click="handleDelete(row)">删除</el-button>
          <el-button
            v-if="!row.forbidden && canSend"
            type="warning"
            link
            @click="handleSend(row)"
          >
            发送
          </el-button>
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
        <el-form-item label="指令代号" prop="cmd_code">
          <el-input
            v-model="form.cmd_code"
            placeholder="请输入指令代号（大写）"
            maxlength="32"
            @input="form.cmd_code = form.cmd_code.toUpperCase()"
          />
        </el-form-item>
        <el-form-item label="指令名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入指令名称" maxlength="128" />
        </el-form-item>
        <el-form-item label="权限等级" prop="permission_level">
          <el-select v-model="form.permission_level" placeholder="请选择权限等级" style="width: 100%">
            <el-option label="观察者 (0)" :value="0" />
            <el-option label="操作员 (1)" :value="1" />
            <el-option label="管理员 (2)" :value="2" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            placeholder="请输入指令描述"
            maxlength="512"
          />
        </el-form-item>
        <el-form-item label="禁止标志">
          <el-switch v-model="form.forbidden" active-text="禁用" inactive-text="正常" />
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
import { commandApi } from '../../api/satellite'

const authStore = useAuthStore()
const { role } = storeToRefs(authStore)
const canEdit = computed(() => role.value === 'admin' || role.value === 'operator')
const canSend = computed(() => role.value === 'admin' || role.value === 'operator')

const loading = ref(false)
const keyword = ref('')
const tableData = ref([])
const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

const dialogVisible = ref(false)
const dialogTitle = ref('新增指令')
const editId = ref(null)
const submitLoading = ref(false)
const formRef = ref(null)

const defaultForm = () => ({
  cmd_code: '',
  name: '',
  permission_level: 1,
  forbidden: false,
  description: ''
})
const form = reactive(defaultForm())

const rules = {
  cmd_code: [
    { required: true, message: '请输入指令代号', trigger: 'blur' },
    { pattern: /^[A-Z][A-Z0-9_]*$/, message: '指令代号须以大写字母开头，仅含大写字母、数字和下划线', trigger: 'blur' }
  ],
  name: [{ required: true, message: '请输入指令名称', trigger: 'blur' }],
  permission_level: [{ required: true, message: '请选择权限等级', trigger: 'change' }]
}

function permissionTagType(level) {
  const map = { 0: 'info', 1: 'warning', 2: 'danger' }
  return map[level] || 'info'
}

function permissionLabel(level) {
  const map = { 0: '观察者', 1: '操作员', 2: '管理员' }
  return map[level] ?? `Lv.${level}`
}

async function fetchData() {
  loading.value = true
  try {
    const res = await commandApi.list({
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
  dialogTitle.value = '新增指令'
  Object.assign(form, defaultForm())
  dialogVisible.value = true
}

function openEdit(row) {
  editId.value = row.id
  dialogTitle.value = '编辑指令'
  Object.assign(form, {
    cmd_code: row.cmd_code || '',
    name: row.name || '',
    permission_level: row.permission_level ?? 1,
    forbidden: !!row.forbidden,
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
      cmd_code: form.cmd_code,
      name: form.name,
      permission_level: form.permission_level,
      forbidden: form.forbidden,
      description: form.description
    }
    if (editId.value) {
      await commandApi.update(editId.value, payload)
      ElMessage.success('指令更新成功')
    } else {
      await commandApi.create(payload)
      ElMessage.success('指令创建成功')
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
      `确认删除指令「${row.cmd_code}」？删除后不可恢复。`,
      '删除确认',
      { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await commandApi.remove(row.id)
    ElMessage.success('指令已删除')
    fetchData()
  } catch { /* 全局拦截已提示 */ }
}

async function handleSend(row) {
  try {
    await ElMessageBox.confirm(
      `确认向卫星发送指令「${row.cmd_code} - ${row.name}」？`,
      '发送确认',
      { confirmButtonText: '确认发送', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await commandApi.send(row.id)
    ElMessage.success('指令已发送')
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
.commands-page {
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

.cmd-code {
  font-family: 'Courier New', Courier, monospace;
  font-size: 13px;
  background: #f0f2f5;
  padding: 2px 6px;
  border-radius: 4px;
  color: #303133;
}

.pagination-wrap {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
