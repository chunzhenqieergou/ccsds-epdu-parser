<template>
  <div class="dashboard">
    <div class="welcome">
      <h3 class="welcome-title">欢迎回来，{{ auth.user?.username || '用户' }}</h3>
      <p class="welcome-time">
        服务器时间：<el-tag type="info" size="small">{{ serverTime }}</el-tag>
        <span style="margin-left: 8px; color: #999; font-size: 12px">{{ greeting }}</span>
      </p>
    </div>

    <el-row :gutter="20" class="stat-cards">
      <el-col :xs="24" :sm="12" :lg="6">
        <div class="stat-card" @click="$router.push('/satellites/list')">
          <div class="stat-icon" style="background: #e6f7ff">
            <el-icon :size="32" color="#1890ff"><Platform /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.satellites }}</div>
            <div class="stat-label">卫星总数</div>
          </div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="12" :lg="6">
        <div class="stat-card" @click="$router.push('/satellites/params')">
          <div class="stat-icon" style="background: #fff7e6">
            <el-icon :size="32" color="#fa8c16"><SetUp /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.params }}</div>
            <div class="stat-label">参数总数</div>
          </div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="12" :lg="6">
        <div class="stat-card" @click="$router.push('/satellites/channels')">
          <div class="stat-icon" style="background: #f6ffed">
            <el-icon :size="32" color="#52c41a"><Connection /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.channels }}</div>
            <div class="stat-label">通道总数</div>
          </div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="12" :lg="6">
        <div class="stat-card" @click="$router.push('/alarms')">
          <div class="stat-icon" style="background: #fff1f0">
            <el-icon :size="32" color="#ff4d4f"><Bell /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.pendingAlarms }}</div>
            <div class="stat-label">待处理告警</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 20px">
      <el-col :span="16">
        <el-card shadow="never">
          <template #header><span>系统简介</span></template>
          <p style="line-height: 1.8; color: #666">
            STMS（卫星遥测数据综合管理系统）是一套基于 CCSDS 标准的卫星遥测数据综合管理平台。
            系统支持多星管理、实时遥测接收、历史数据查询、统计分析、曲线绘制、数据导出和告警管理等功能。
          </p>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never">
          <template #header><span>快速导航</span></template>
          <div class="quick-links">
            <el-link type="primary" @click="$router.push('/realtime')">实时遥测</el-link>
            <el-link type="primary" @click="$router.push('/history')">历史查询</el-link>
            <el-link type="primary" @click="$router.push('/statistics')">统计分析</el-link>
            <el-link type="primary" @click="$router.push('/curves')">曲线绘制</el-link>
            <el-link type="primary" @click="$router.push('/export-data')">数据导出</el-link>
            <el-link type="primary" @click="$router.push('/alarms')">告警中心</el-link>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import dayjs from 'dayjs'
import { useAuthStore } from '../stores/auth'
import { satelliteApi, paramApi, channelApi } from '../api/satellite'
import { alarmApi } from '../api/telemetry'
import { timeApi } from '../api/system'

const auth = useAuthStore()

const serverTime = ref('--')
const stats = reactive({
  satellites: 0,
  params: 0,
  channels: 0,
  pendingAlarms: 0
})

const greeting = computed(() => {
  const h = dayjs().hour()
  if (h < 6) return '夜深了，注意休息'
  if (h < 9) return '早上好'
  if (h < 12) return '上午好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
})

let timeTimer = null

async function fetchTime() {
  try {
    const data = await timeApi.current()
    serverTime.value = dayjs(data?.current_time || data?.time || data).format('YYYY-MM-DD HH:mm:ss')
  } catch {
    serverTime.value = dayjs().format('YYYY-MM-DD HH:mm:ss')
  }
}

async function fetchStats() {
  try {
    const [satellites, params, channels, alarmStats] = await Promise.allSettled([
      satelliteApi.list({ limit: 1 }),
      paramApi.list({ limit: 1 }),
      channelApi.list({ limit: 1 }),
      alarmApi.stats()
    ])
    if (satellites.status === 'fulfilled') {
      const d = satellites.value
      stats.satellites = d.total || d.count || (Array.isArray(d) ? d.length : 0)
    }
    if (params.status === 'fulfilled') {
      const d = params.value
      stats.params = d.total || d.count || (Array.isArray(d) ? d.length : 0)
    }
    if (channels.status === 'fulfilled') {
      const d = channels.value
      stats.channels = d.total || d.count || (Array.isArray(d) ? d.length : 0)
    }
    if (alarmStats.status === 'fulfilled') {
      const d = alarmStats.value
      // 兼容多种返回结构：优先 pending / unhandled / pending_count，回退 by_status.status_0
      stats.pendingAlarms = d.pending ?? d.unhandled ?? d.pending_count
        ?? d.by_status?.status_0 ?? 0
    }
  } catch {}
}

onMounted(() => {
  fetchTime()
  fetchStats()
  timeTimer = setInterval(fetchTime, 30000)
})

onUnmounted(() => {
  if (timeTimer) clearInterval(timeTimer)
})
</script>

<style scoped>
.dashboard { max-width: 1200px; }
.welcome { margin-bottom: 20px; }
.welcome-title { margin: 0 0 4px; font-size: 22px; color: #1a1a2e; }
.welcome-time { margin: 0; color: #666; font-size: 14px; }
.stat-cards { margin-top: 0; }
.stat-card {
  background: #fff;
  border-radius: 8px;
  padding: 24px;
  display: flex;
  align-items: center;
  gap: 20px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  cursor: pointer;
  transition: box-shadow 0.2s;
}
.stat-card:hover { box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12); }
.stat-icon {
  width: 64px;
  height: 64px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.stat-value { font-size: 28px; font-weight: 700; color: #1a1a2e; line-height: 1.2; }
.stat-label { font-size: 14px; color: #999; margin-top: 4px; }
.quick-links { display: flex; flex-wrap: wrap; gap: 12px; }
.quick-links .el-link { margin-right: 0; }
</style>
