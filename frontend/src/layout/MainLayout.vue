<template>
  <el-container class="main-layout">
    <el-aside :width="isCollapse ? '64px' : '220px'" class="sidebar">
      <div class="logo" @click="$router.push('/dashboard')">
        <img src="/vite.svg" alt="logo" class="logo-img" />
        <span v-show="!isCollapse" class="logo-text">STMS</span>
      </div>

      <el-menu
        :default-active="activeMenu"
        :collapse="isCollapse"
        :collapse-transition="false"
        router
        background-color="#001529"
        text-color="#ffffffa6"
        active-text-color="#fff"
        class="sidebar-menu"
      >
        <el-menu-item index="/dashboard">
          <el-icon><HomeFilled /></el-icon>
          <span>首页看板</span>
        </el-menu-item>

        <el-menu-item index="/realtime">
          <el-icon><Monitor /></el-icon>
          <span>实时遥测</span>
        </el-menu-item>

        <el-menu-item index="/history">
          <el-icon><Search /></el-icon>
          <span>历史查询</span>
        </el-menu-item>

        <el-menu-item index="/statistics">
          <el-icon><DataAnalysis /></el-icon>
          <span>统计分析</span>
        </el-menu-item>

        <el-menu-item index="/curves">
          <el-icon><TrendCharts /></el-icon>
          <span>曲线绘制</span>
        </el-menu-item>

        <el-menu-item index="/export-data">
          <el-icon><Download /></el-icon>
          <span>数据导出</span>
        </el-menu-item>

        <el-menu-item index="/alarms">
          <el-icon><Bell /></el-icon>
          <span>告警管理</span>
        </el-menu-item>

        <el-sub-menu index="satellites">
          <template #title>
            <el-icon><Platform /></el-icon>
            <span>卫星配置</span>
          </template>
          <el-menu-item index="/satellites/list">卫星管理</el-menu-item>
          <el-menu-item index="/satellites/params">参数配置</el-menu-item>
          <el-menu-item index="/satellites/channels">通道配置</el-menu-item>
        </el-sub-menu>

        <el-sub-menu v-if="auth.role === 'admin'" index="system">
          <template #title>
            <el-icon><Setting /></el-icon>
            <span>系统管理</span>
          </template>
          <el-menu-item index="/system/users">用户管理</el-menu-item>
          <el-menu-item index="/system/roles">角色管理</el-menu-item>
          <el-menu-item index="/system/logs">操作日志</el-menu-item>
        </el-sub-menu>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="topbar" height="56px">
        <div class="topbar-left">
          <el-icon class="collapse-btn" @click="isCollapse = !isCollapse">
            <Fold v-if="!isCollapse" />
            <Expand v-else />
          </el-icon>
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/dashboard' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item v-if="currentTitle">{{ currentTitle }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>

        <div class="topbar-right">
          <el-dropdown trigger="click" @command="handleUserCommand">
            <span class="user-info">
              <el-icon><UserFilled /></el-icon>
              <span class="username">{{ auth.user?.username || '用户' }}</span>
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="changePassword">
                  <el-icon><Lock /></el-icon>修改密码
                </el-dropdown-item>
                <el-dropdown-item divided command="logout">
                  <el-icon><SwitchButton /></el-icon>退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>

  <el-dialog v-model="pwdDialogVisible" title="修改密码" width="420px" :close-on-click-modal="false">
    <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" label-width="80px" size="default">
      <el-form-item label="旧密码" prop="old_password">
        <el-input v-model="pwdForm.old_password" type="password" show-password placeholder="请输入旧密码" />
      </el-form-item>
      <el-form-item label="新密码" prop="new_password">
        <el-input v-model="pwdForm.new_password" type="password" show-password placeholder="请输入新密码" />
      </el-form-item>
      <el-form-item label="确认密码" prop="confirm_password">
        <el-input v-model="pwdForm.confirm_password" type="password" show-password placeholder="请再次输入新密码" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="pwdDialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="pwdLoading" @click="handleChangePassword">确认</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const isCollapse = ref(false)

const activeMenu = computed(() => {
  const { path } = route
  if (path.startsWith('/satellites')) return 'satellites'
  if (path.startsWith('/system')) return 'system'
  return path
})

const currentTitle = computed(() => route.meta?.title || '')

function handleUserCommand(command) {
  if (command === 'changePassword') {
    pwdForm.old_password = ''
    pwdForm.new_password = ''
    pwdForm.confirm_password = ''
    pwdDialogVisible.value = true
  } else if (command === 'logout') {
    ElMessageBox.confirm('确定要退出登录吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }).then(() => {
      auth.logout()
      router.push('/login')
    }).catch(() => {})
  }
}

const pwdDialogVisible = ref(false)
const pwdLoading = ref(false)
const pwdFormRef = ref(null)

const pwdForm = ref({
  old_password: '',
  new_password: '',
  confirm_password: ''
})

const validateConfirmPassword = (rule, value, callback) => {
  if (value !== pwdForm.value.new_password) {
    callback(new Error('两次输入的密码不一致'))
  } else {
    callback()
  }
}

const pwdRules = {
  old_password: [{ required: true, message: '请输入旧密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, max: 128, message: '密码长度为 6-128 位', trigger: 'blur' }
  ],
  confirm_password: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    { validator: validateConfirmPassword, trigger: 'blur' }
  ]
}

async function handleChangePassword() {
  if (!pwdFormRef.value) return
  try {
    await pwdFormRef.value.validate()
  } catch {
    return
  }
  pwdLoading.value = true
  try {
    await auth.changePassword({
      old_password: pwdForm.old_password,
      new_password: pwdForm.new_password
    })
    ElMessage.success('密码修改成功，请重新登录')
    pwdDialogVisible.value = false
    auth.logout()
    router.push('/login')
  } catch {
  } finally {
    pwdLoading.value = false
  }
}
</script>

<style scoped>
.main-layout {
  height: 100vh;
}

.sidebar {
  background: linear-gradient(180deg, #001529 0%, #002140 100%);
  overflow: hidden;
  transition: width 0.3s ease;
}

.logo {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  cursor: pointer;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.02);
}

.logo-img {
  width: 30px;
  height: 30px;
  filter: drop-shadow(0 0 6px rgba(64, 158, 255, 0.4));
}

.logo-text {
  color: #fff;
  font-size: 18px;
  font-weight: 700;
  white-space: nowrap;
  letter-spacing: 2px;
}

.sidebar-menu {
  border-right: none;
}

.sidebar-menu:not(.el-menu--collapse) {
  width: 220px;
}

.sidebar-menu :deep(.el-menu-item):hover {
  background-color: rgba(255, 255, 255, 0.06) !important;
}

.sidebar-menu :deep(.el-menu-item.is-active) {
  background: linear-gradient(90deg, #1890ff, #096dd9) !important;
  border-radius: 0 4px 4px 0;
  margin: 4px 8px;
  width: calc(100% - 16px);
}

.sidebar-menu :deep(.el-sub-menu__title):hover {
  background-color: rgba(255, 255, 255, 0.06) !important;
}

.topbar {
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  border-bottom: 1px solid #e8e8e8;
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.06);
  z-index: 10;
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 18px;
}

.collapse-btn {
  font-size: 20px;
  cursor: pointer;
  color: #666;
  transition: color 0.2s, transform 0.2s;
}

.collapse-btn:hover {
  color: #1890ff;
  transform: scale(1.1);
}

.user-info {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  color: #333;
  font-size: 14px;
  padding: 6px 12px;
  border-radius: 6px;
  transition: all 0.2s;
}

.user-info:hover {
  color: #1890ff;
  background: rgba(24, 144, 255, 0.06);
}

.main-content {
  background: linear-gradient(180deg, #f0f2f5 0%, #f5f7fa 100%);
  padding: 24px;
  overflow-y: auto;
  min-height: 0;
}
</style>
