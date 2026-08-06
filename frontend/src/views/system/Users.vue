<template>
  <div class="users-page">
    <div class="page-header">
      <h3 class="page-title">用户管理</h3>
      <p class="page-desc">管理系统用户账号</p>
    </div>

    <el-card shadow="never">
      <div class="toolbar">
        <el-input v-model="searchKeyword" placeholder="搜索用户名/邮箱" style="width: 260px" clearable @clear="fetchUsers" @keyup.enter="fetchUsers" />
        <el-button type="primary" @click="openCreateDialog">新增用户</el-button>
      </div>

      <el-table :data="users" v-loading="loading" stripe size="default" style="margin-top: 12px">
        <el-table-column prop="username" label="用户名" width="140" />
        <el-table-column prop="email" label="邮箱" min-width="180" show-overflow-tooltip />
        <el-table-column prop="role" label="角色" width="120">
          <template #default="{ row }">
            <el-tag :type="roleTagType(row.role)" size="small">{{ row.role }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_active !== false ? 'success' : 'info'" size="small">
              {{ row.is_active !== false ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openEditDialog(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="deleteUser(row)">删除</el-button>
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
          @current-change="fetchUsers"
          @size-change="fetchUsers"
        />
      </div>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="480px" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px" size="default">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="请输入用户名" :disabled="isEdit" />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="form.email" placeholder="请输入邮箱" />
        </el-form-item>
        <el-form-item v-if="!isEdit" label="密码" prop="password">
          <el-input v-model="form.password" type="password" show-password placeholder="请输入密码" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="form.role" placeholder="请选择角色" style="width: 100%">
            <el-option label="管理员 (admin)" value="admin" />
            <el-option label="操作员 (operator)" value="operator" />
            <el-option label="观察者 (observer)" value="observer" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.is_active" active-text="启用" inactive-text="禁用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="doSubmit">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'
import { userApi } from '../../api/system'

const loading = ref(false)
const users = ref([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const searchKeyword = ref('')

const dialogVisible = ref(false)
const dialogTitle = computed(() => (editingUser.value ? '编辑用户' : '新增用户'))
const isEdit = computed(() => !!editingUser.value)
const editingUser = ref(null)
const submitLoading = ref(false)
const formRef = ref(null)

const form = reactive({
  username: '',
  email: '',
  password: '',
  role: 'observer',
  is_active: true
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' }
  ],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }, { min: 6, message: '密码至少6位', trigger: 'blur' }],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }]
}

function roleTagType(role) {
  const map = { admin: 'danger', operator: 'warning', observer: 'info' }
  return map[role] || 'info'
}

function formatTime(t) {
  return t ? dayjs(t).format('YYYY-MM-DD HH:mm:ss') : '-'
}

async function fetchUsers() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (searchKeyword.value) params.keyword = searchKeyword.value
    const data = await userApi.list(params)
    if (Array.isArray(data)) {
      users.value = data
      total.value = data.length
    } else {
      users.value = data.items || data.users || []
      total.value = data.total || data.count || users.value.length
    }
  } catch {} finally {
    loading.value = false
  }
}

function resetForm() {
  form.username = ''
  form.email = ''
  form.password = ''
  form.role = 'observer'
  form.is_active = true
}

function openCreateDialog() {
  editingUser.value = null
  resetForm()
  dialogVisible.value = true
}

function openEditDialog(row) {
  editingUser.value = row
  form.username = row.username || ''
  form.email = row.email || ''
  form.password = ''
  form.role = row.role || 'observer'
  form.is_active = row.is_active !== false
  dialogVisible.value = true
}

async function doSubmit() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch { return }
  submitLoading.value = true
  try {
    const data = {
      username: form.username,
      email: form.email,
      role: form.role,
      is_active: form.is_active
    }
    if (!isEdit.value) {
      data.password = form.password
      await userApi.create(data)
      ElMessage.success('用户创建成功')
    } else {
      if (form.password) data.password = form.password
      await userApi.update(editingUser.value.id, data)
      ElMessage.success('用户更新成功')
    }
    dialogVisible.value = false
    fetchUsers()
  } catch {} finally {
    submitLoading.value = false
  }
}

async function deleteUser(row) {
  try {
    await ElMessageBox.confirm(`确定要删除用户「${row.username}」吗？此操作不可撤销。`, '确认删除', {
      type: 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消'
    })
  } catch { return }
  try {
    await userApi.remove(row.id)
    ElMessage.success('已删除')
    fetchUsers()
  } catch {}
}

onMounted(fetchUsers)
</script>

<style scoped>
.users-page { }
.page-header { margin-bottom: 16px; }
.page-title { margin: 0 0 4px; font-size: 20px; color: #1a1a2e; }
.page-desc { margin: 0; color: #999; font-size: 14px; }
.toolbar { display: flex; gap: 12px; align-items: center; }
</style>
