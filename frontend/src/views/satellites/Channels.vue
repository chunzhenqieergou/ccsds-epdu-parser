<template>
  <div class="channels-page">
    <div class="page-header">
      <h3 class="page-title">通道管理</h3>
      <p class="page-desc">管理与卫星通信的数据通道，支持启停控制</p>
    </div>

    <div class="toolbar">
      <div class="toolbar-left">
        <el-input
          v-model="keyword"
          placeholder="搜索通道名称"
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
          新增通道
        </el-button>
      </div>
    </div>

    <el-table :data="tableData" v-loading="loading" border stripe>
      <el-table-column prop="name" label="通道名称" min-width="140" />
      <el-table-column prop="protocol_type" label="协议类型" width="110" align="center">
        <template #default="{ row }">
          <el-tag :type="protocolTagType(row.protocol_type)" size="small">
            {{ row.protocol_type || '-' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="ip" label="IP 地址" min-width="140" />
      <el-table-column prop="port" label="端口" width="90" align="center" />
      <el-table-column prop="baud_rate" label="波特率" width="110" align="center">
        <template #default="{ row }">
          {{ row.baud_rate ? row.baud_rate.toLocaleString() : '-' }}
        </template>
      </el-table-column>
      <el-table-column prop="running" label="运行状态" width="100" align="center">
        <template #default="{ row }">
          <el-switch
            v-if="canEdit"
            :model-value="!!row.running"
            :loading="row._toggling"
            @change="(val) => handleToggleRunning(row, val)"
          />
          <el-tag v-else :type="row.running ? 'success' : 'info'" size="small">
            {{ row.running ? '运行中' : '已停止' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="160" show-overflow-tooltip />
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
        <el-form-item label="协议类型" prop="protocol_type">
          <el-select v-model="form.protocol_type" placeholder="请选择协议类型" style="width: 100%">
            <el-option v-for="p in protocolTypes" :key="p" :label="p" :value="p" />
          </el-select>
        </el-form-item>
        <el-form-item label="通道名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入通道名称" maxlength="64" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="16">
            <el-form-item label="IP 地址" prop="ip">
              <el-input v-model="form.ip" placeholder="请输入 IP 地址" maxlength="45" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="端口" prop="port">
              <el-input-number v-model="form.port" :min="1" :max="65535" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="波特率" prop="baud_rate">
              <el-input-number v-model="form.baud_rate" :min="0" :step="1200" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="帧格式" prop="frame_format">
              <el-input v-model="form.frame_format" placeholder="请输入帧格式" maxlength="32" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="运行状态">
          <el-switch v-model="form.running" active-text="启动" inactive-text="停止" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input
            v-model="form.remark"
            type="textarea"
            :rows="3"
            placeholder="请输入备注信息"
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
import { channelApi } from '../../api/satellite'

const authStore = useAuthStore()
const { role } = storeToRefs(authStore)
const canEdit = computed(() => role.value === 'admin' || role.value === 'operator')

const protocolTypes = ['CCSDS', '1553B', 'CAN', 'RS422']

const loading = ref(false)
const keyword = ref('')
const tableData = ref([])
const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

const dialogVisible = ref(false)
const dialogTitle = ref('新增通道')
const editId = ref(null)
const submitLoading = ref(false)
const formRef = ref(null)

const defaultForm = () => ({
  protocol_type: '',
  name: '',
  ip: '',
  port: null,
  baud_rate: null,
  frame_format: '',
  running: false,
  remark: ''
})
const form = reactive(defaultForm())

const rules = {
  protocol_type: [{ required: true, message: '请选择协议类型', trigger: 'change' }],
  name: [{ required: true, message: '请输入通道名称', trigger: 'blur' }],
  ip: [{ required: true, message: '请输入 IP 地址', trigger: 'blur' }],
  port: [{ required: true, message: '请输入端口', trigger: 'blur' }]
}

function protocolTagType(type) {
  const map = { CCSDS: '', '1553B': 'success', CAN: 'warning', RS422: 'danger' }
  return map[type] || 'info'
}

async function fetchData() {
  loading.value = true
  try {
    const res = await channelApi.list({
      page: pagination.page,
      page_size: pagination.pageSize,
      keyword: keyword.value
    })
    tableData.value = (res.items || []).map((item) => ({
      ...item,
      _toggling: false
    }))
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
  dialogTitle.value = '新增通道'
  Object.assign(form, defaultForm())
  dialogVisible.value = true
}

function openEdit(row) {
  editId.value = row.id
  dialogTitle.value = '编辑通道'
  Object.assign(form, {
    protocol_type: row.protocol_type || '',
    name: row.name || '',
    ip: row.ip || '',
    port: row.port ?? null,
    baud_rate: row.baud_rate ?? null,
    frame_format: row.frame_format || '',
    running: !!row.running,
    remark: row.remark || ''
  })
  dialogVisible.value = true
}

async function handleSubmit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  submitLoading.value = true
  try {
    const payload = {
      protocol_type: form.protocol_type,
      name: form.name,
      ip: form.ip,
      port: form.port,
      baud_rate: form.baud_rate,
      frame_format: form.frame_format,
      running: form.running,
      remark: form.remark
    }
    if (editId.value) {
      await channelApi.update(editId.value, payload)
      ElMessage.success('通道更新成功')
    } else {
      await channelApi.create(payload)
      ElMessage.success('通道创建成功')
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
      `确认删除通道「${row.name}」？删除后不可恢复。`,
      '删除确认',
      { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await channelApi.remove(row.id)
    ElMessage.success('通道已删除')
    fetchData()
  } catch { /* 全局拦截已提示 */ }
}

async function handleToggleRunning(row, val) {
  row._toggling = true
  try {
    if (val) {
      await channelApi.start(row.id)
    } else {
      await channelApi.stop(row.id)
    }
    row.running = val
    ElMessage.success(val ? '通道已启动' : '通道已停止')
  } catch {
    /* 全局拦截已提示 */
  } finally {
    row._toggling = false
  }
}

function handleDialogClosed() {
  formRef.value?.resetFields()
}

onMounted(() => {
  fetchData()
})
</script>

<style scoped>
.channels-page {
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
