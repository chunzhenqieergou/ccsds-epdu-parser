<template>
  <div class="dashboard">
    <div class="welcome-banner">
      <div class="welcome-info">
        <h3 class="welcome-title">欢迎回来，{{ auth.user?.username || '用户' }}</h3>
        <p class="welcome-subtitle">{{ greeting }} · 卫星遥测数据综合管理系统</p>
      </div>
      <div class="welcome-meta">
        <el-tag type="info" size="default" effect="plain">
          <el-icon style="margin-right: 4px"><Clock /></el-icon>
          服务器时间：{{ serverTime }}
        </el-tag>
      </div>
    </div>

    <el-row :gutter="20" class="stat-cards">
      <el-col :xs="24" :sm="12" :lg="6">
        <div class="stat-card card-blue" @click="$router.push('/satellites/list')">
          <div class="stat-card-inner">
            <div class="stat-icon-wrap">
              <el-icon :size="28"><Platform /></el-icon>
            </div>
            <div class="stat-body">
              <div class="stat-value">{{ stats.satellites }}</div>
              <div class="stat-label">卫星总数</div>
            </div>
          </div>
          <div class="stat-card-footer">
            <span>查看详情</span>
            <el-icon :size="14"><ArrowRight /></el-icon>
          </div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="12" :lg="6">
        <div class="stat-card card-orange" @click="$router.push('/satellites/params')">
          <div class="stat-card-inner">
            <div class="stat-icon-wrap">
              <el-icon :size="28"><SetUp /></el-icon>
            </div>
            <div class="stat-body">
              <div class="stat-value">{{ stats.params }}</div>
              <div class="stat-label">参数总数</div>
            </div>
          </div>
          <div class="stat-card-footer">
            <span>查看详情</span>
            <el-icon :size="14"><ArrowRight /></el-icon>
          </div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="12" :lg="6">
        <div class="stat-card card-green" @click="$router.push('/satellites/channels')">
          <div class="stat-card-inner">
            <div class="stat-icon-wrap">
              <el-icon :size="28"><Connection /></el-icon>
            </div>
            <div class="stat-body">
              <div class="stat-value">{{ stats.channels }}</div>
              <div class="stat-label">通道总数</div>
            </div>
          </div>
          <div class="stat-card-footer">
            <span>查看详情</span>
            <el-icon :size="14"><ArrowRight /></el-icon>
          </div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="12" :lg="6">
        <div class="stat-card card-red" @click="$router.push('/alarms')">
          <div class="stat-card-inner">
            <div class="stat-icon-wrap">
              <el-icon :size="28"><Bell /></el-icon>
            </div>
            <div class="stat-body">
              <div class="stat-value">{{ stats.pendingAlarms }}</div>
              <div class="stat-label">待处理告警</div>
            </div>
          </div>
          <div class="stat-card-footer">
            <span>查看详情</span>
            <el-icon :size="14"><ArrowRight /></el-icon>
          </div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="content-row">
      <el-col :xs="24" :lg="16">
        <el-card shadow="never" class="info-card">
          <template #header>
            <div class="card-header">
              <span>系统简介</span>
              <el-tag type="primary" size="small" effect="light">v2.0</el-tag>
            </div>
          </template>
          <div class="system-intro">
            <p>
              <strong>STMS</strong>（卫星遥测数据综合管理系统）是一套基于 CCSDS 标准的卫星遥测数据综合管理平台。
              系统支持多星管理、实时遥测接收、历史数据查询、统计分析、曲线绘制、数据导出和告警管理等功能，
              为卫星地面测控提供全方位的遥测数据处理解决方案。
            </p>
            <div class="feature-grid">
              <div class="feature-item">
                <el-icon color="#1890ff" :size="18"><Monitor /></el-icon>
                <span>实时遥测监控</span>
              </div>
              <div class="feature-item">
                <el-icon color="#52c41a" :size="18"><Search /></el-icon>
                <span>历史数据回溯</span>
              </div>
              <div class="feature-item">
                <el-icon color="#fa8c16" :size="18"><DataAnalysis /></el-icon>
                <span>智能统计分析</span>
              </div>
              <div class="feature-item">
                <el-icon color="#722ed1" :size="18"><TrendCharts /></el-icon>
                <span>多维曲线展示</span>
              </div>
              <div class="feature-item">
                <el-icon color="#eb2f96" :size="18"><Download /></el-icon>
                <span>多元格式导出</span>
              </div>
              <div class="feature-item">
                <el-icon color="#ff4d4f" :size="18"><Bell /></el-icon>
                <span>实时告警中心</span>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="8">
        <el-card shadow="never" class="quick-card">
          <template #header>
            <div class="card-header">
              <span>快速导航</span>
            </div>
          </template>
          <div class="quick-links">
            <div class="quick-link-item" @click="$router.push('/realtime')">
              <el-icon :size="20" color="#1890ff"><Monitor /></el-icon>
              <div class="quick-link-text">
                <span class="quick-link-title">实时遥测</span>
                <span class="quick-link-desc">实时数据流监控</span>
              </div>
            </div>
            <div class="quick-link-item" @click="$router.push('/history')">
              <el-icon :size="20" color="#52c41a"><Search /></el-icon>
              <div class="quick-link-text">
                <span class="quick-link-title">历史查询</span>
                <span class="quick-link-desc">历史数据检索回放</span>
              </div>
            </div>
            <div class="quick-link-item" @click="$router.push('/statistics')">
              <el-icon :size="20" color="#fa8c16"><DataAnalysis /></el-icon>
              <div class="quick-link-text">
                <span class="quick-link-title">统计分析</span>
                <span class="quick-link-desc">数据统计与趋势</span>
              </div>
            </div>
            <div class="quick-link-item" @click="$router.push('/curves')">
              <el-icon :size="20" color="#722ed1"><TrendCharts /></el-icon>
              <div class="quick-link-text">
                <span class="quick-link-title">曲线绘制</span>
                <span class="quick-link-desc">多维曲线可视化</span>
              </div>
            </div>
            <div class="quick-link-item" @click="$router.push('/export-data')">
              <el-icon :size="20" color="#eb2f96"><Download /></el-icon>
              <div class="quick-link-text">
                <span class="quick-link-title">数据导出</span>
                <span class="quick-link-desc">多格式数据导出</span>
              </div>
            </div>
            <div class="quick-link-item" @click="$router.push('/alarms')">
              <el-icon :size="20" color="#ff4d4f"><Bell /></el-icon>
              <div class="quick-link-text">
                <span class="quick-link-title">告警中心</span>
                <span class="quick-link-desc">告警监控与处理</span>
              </div>
            </div>
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
let tickTimer = null
let serverOffset = 0 // 服务器时间 - 本地时间（毫秒）

function tick() {
  serverTime.value = dayjs(Date.now() + serverOffset).format('YYYY-MM-DD HH:mm:ss')
}

async function fetchTime() {
  try {
    const data = await timeApi.current()
    const serverTs = dayjs(data?.server_time || data?.current_time || data?.time).valueOf()
    if (serverTs) {
      serverOffset = serverTs - Date.now()
    }
    tick()
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
      stats.pendingAlarms = d.pending ?? d.unhandled ?? d.pending_count
        ?? d.by_status?.status_0 ?? 0
    }
  } catch {}
}

onMounted(() => {
  fetchTime()
  fetchStats()
  tickTimer = setInterval(tick, 1000)
  timeTimer = setInterval(fetchTime, 30000)
})

onUnmounted(() => {
  if (timeTimer) clearInterval(timeTimer)
  if (tickTimer) clearInterval(tickTimer)
})
</script>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.welcome-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 28px 32px;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 40%, #0f3460 100%);
  border-radius: 12px;
  color: #fff;
  position: relative;
  overflow: hidden;
}

.welcome-banner::before {
  content: '';
  position: absolute;
  top: -50%;
  right: -10%;
  width: 300px;
  height: 300px;
  background: radial-gradient(circle, rgba(24, 144, 255, 0.15), transparent 70%);
  border-radius: 50%;
}

.welcome-banner::after {
  content: '';
  position: absolute;
  bottom: -30%;
  left: 20%;
  width: 200px;
  height: 200px;
  background: radial-gradient(circle, rgba(114, 46, 209, 0.12), transparent 70%);
  border-radius: 50%;
}

.welcome-info {
  position: relative;
  z-index: 1;
}

.welcome-title {
  margin: 0 0 6px;
  font-size: 24px;
  font-weight: 600;
}

.welcome-subtitle {
  margin: 0;
  font-size: 14px;
  color: rgba(255, 255, 255, 0.7);
}

.welcome-meta {
  position: relative;
  z-index: 1;
}

.stat-cards {
  margin: 0;
}

.stat-card {
  background: #fff;
  border-radius: 10px;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.3s ease;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  border: 1px solid transparent;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.12);
}

.stat-card-inner {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 22px 24px 14px;
}

.stat-icon-wrap {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.card-blue .stat-icon-wrap {
  background: linear-gradient(135deg, #e6f7ff, #bae7ff);
  color: #1890ff;
}

.card-orange .stat-icon-wrap {
  background: linear-gradient(135deg, #fff7e6, #ffe7ba);
  color: #fa8c16;
}

.card-green .stat-icon-wrap {
  background: linear-gradient(135deg, #f6ffed, #d9f7be);
  color: #52c41a;
}

.card-red .stat-icon-wrap {
  background: linear-gradient(135deg, #fff1f0, #ffccc7);
  color: #ff4d4f;
}

.stat-body {
  flex: 1;
}

.stat-value {
  font-size: 30px;
  font-weight: 700;
  color: #1a1a2e;
  line-height: 1.2;
}

.stat-label {
  font-size: 14px;
  color: #999;
  margin-top: 2px;
}

.stat-card-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 10px;
  font-size: 13px;
  color: #999;
  border-top: 1px solid #f0f0f0;
  transition: all 0.2s;
}

.stat-card:hover .stat-card-footer {
  color: #1890ff;
  background: #fafafa;
}

.stat-card:hover.card-blue { border-color: #91caff; }
.stat-card:hover.card-orange { border-color: #ffd591; }
.stat-card:hover.card-green { border-color: #b7eb8f; }
.stat-card:hover.card-red { border-color: #ffa39e; }

.content-row {
  margin: 0;
}

.info-card, .quick-card {
  border-radius: 10px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.info-card :deep(.el-card__header),
.quick-card :deep(.el-card__header) {
  border-bottom: 1px solid #f0f0f0;
  padding: 16px 20px;
}

.info-card :deep(.el-card__body),
.quick-card :deep(.el-card__body) {
  padding: 20px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
  font-size: 15px;
  color: #1a1a2e;
}

.system-intro p {
  line-height: 1.9;
  color: #555;
  margin: 0 0 20px;
  font-size: 14px;
}

.feature-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: #fafafa;
  border-radius: 8px;
  font-size: 13px;
  color: #555;
  transition: all 0.2s;
}

.feature-item:hover {
  background: #f0f5ff;
  color: #1890ff;
}

.quick-links {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.quick-link-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 14px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.quick-link-item:hover {
  background: #f5f7fa;
}

.quick-link-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.quick-link-title {
  font-size: 14px;
  color: #333;
  font-weight: 500;
}

.quick-link-desc {
  font-size: 12px;
  color: #999;
}

@media (max-width: 768px) {
  .welcome-banner {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
    padding: 20px;
  }
  .feature-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
