import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('../views/Login.vue'),
      meta: { guest: true }
    },
    {
      path: '/register',
      name: 'Register',
      component: () => import('../views/Register.vue'),
      meta: { guest: true }
    },
    {
      path: '/',
      component: () => import('../layout/MainLayout.vue'),
      redirect: '/dashboard',
      children: [
        {
          path: 'dashboard',
          name: 'Dashboard',
          component: () => import('../views/Dashboard.vue'),
          meta: { title: '首页看板' }
        },
        {
          path: 'realtime',
          name: 'Realtime',
          component: () => import('../views/Realtime.vue'),
          meta: { title: '实时遥测' }
        },
        {
          path: 'history',
          name: 'History',
          component: () => import('../views/History.vue'),
          meta: { title: '历史查询' }
        },
        {
          path: 'statistics',
          name: 'Statistics',
          component: () => import('../views/Statistics.vue'),
          meta: { title: '统计分析' }
        },
        {
          path: 'curves',
          name: 'Curves',
          component: () => import('../views/Curves.vue'),
          meta: { title: '曲线绘制' }
        },
        {
          path: 'export-data',
          name: 'ExportData',
          component: () => import('../views/ExportData.vue'),
          meta: { title: '数据导出' }
        },
        {
          path: 'alarms',
          name: 'Alarms',
          component: () => import('../views/Alarms.vue'),
          meta: { title: '告警管理' }
        },
        {
          path: 'satellites/list',
          name: 'SatelliteList',
          component: () => import('../views/satellites/SatelliteList.vue'),
          meta: { title: '卫星管理', parent: 'satellites' }
        },
        {
          path: 'satellites/params',
          name: 'SatelliteParams',
          component: () => import('../views/satellites/Params.vue'),
          meta: { title: '参数配置', parent: 'satellites' }
        },
        {
          path: 'satellites/channels',
          name: 'SatelliteChannels',
          component: () => import('../views/satellites/Channels.vue'),
          meta: { title: '通道配置', parent: 'satellites' }
        },
        {
          path: 'system/users',
          name: 'SystemUsers',
          component: () => import('../views/system/Users.vue'),
          meta: { title: '用户管理', parent: 'system', role: 'admin' }
        },
        {
          path: 'system/roles',
          name: 'SystemRoles',
          component: () => import('../views/system/Roles.vue'),
          meta: { title: '角色管理', parent: 'system', role: 'admin' }
        },
        {
          path: 'system/logs',
          name: 'SystemLogs',
          component: () => import('../views/system/Logs.vue'),
          meta: { title: '操作日志', parent: 'system', role: 'admin' }
        }
      ]
    }
  ]
})

router.beforeEach(async (to, from, next) => {
  const auth = useAuthStore()
  const token = auth.token

  if (to.meta.guest) {
    if (token) {
      return next('/')
    }
    return next()
  }

  if (!token) {
    return next('/login')
  }

  if (!auth.user) {
    try {
      await auth.fetchMe()
    } catch {
      auth.logout()
      return next('/login')
    }
  }

  if (to.meta.role && auth.user.role !== to.meta.role) {
    return next('/dashboard')
  }

  next()
})

export default router
