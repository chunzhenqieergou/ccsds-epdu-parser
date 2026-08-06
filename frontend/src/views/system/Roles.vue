<template>
  <div class="roles-page">
    <div class="page-header">
      <h3 class="page-title">角色管理</h3>
      <p class="page-desc">查看系统角色及其权限配置</p>
    </div>

    <el-card shadow="never">
      <el-table :data="roles" v-loading="loading" stripe size="default">
        <el-table-column prop="name" label="角色名称" width="160" />
        <el-table-column prop="display_name" label="显示名称" width="160">
          <template #default="{ row }">{{ row.display_name || row.name }}</template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
        <el-table-column label="权限列表" min-width="300">
          <template #default="{ row }">
            <el-tag
              v-for="perm in row.permissions || row.perm_list || row.menus || []"
              :key="perm"
              size="small"
              style="margin: 2px 4px 2px 0"
            >
              {{ perm }}
            </el-tag>
            <span v-if="!(row.permissions || row.perm_list || row.menus)?.length" style="color: #999">暂无权限配置</span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import dayjs from 'dayjs'
import { roleApi } from '../../api/system'

const loading = ref(false)
const roles = ref([])

function formatTime(t) {
  return t ? dayjs(t).format('YYYY-MM-DD HH:mm:ss') : '-'
}

async function fetchRoles() {
  loading.value = true
  try {
    const data = await roleApi.list()
    roles.value = Array.isArray(data) ? data : (data.items || data.roles || [])
  } catch {} finally {
    loading.value = false
  }
}

onMounted(fetchRoles)
</script>

<style scoped>
.roles-page { }
.page-header { margin-bottom: 16px; }
.page-title { margin: 0 0 4px; font-size: 20px; color: #1a1a2e; }
.page-desc { margin: 0; color: #999; font-size: 14px; }
</style>
