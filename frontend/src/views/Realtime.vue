<template>
  <div class="realtime-page">
    <div class="status-bar">
      <div class="status-left">
        <el-tag :type="statusTagType" size="small">
          {{ statusText }}
        </el-tag>
        <el-divider direction="vertical" />
        <span class="stat-item">帧数: <b>{{ store.frameCount }}</b></span>
        <span class="stat-item">错误: <b>{{ store.errorCount }}</b></span>
        <span v-if="store.lastHeartbeat" class="stat-item">
          心跳: {{ dayjs(store.lastHeartbeat).format('HH:mm:ss') }}
        </span>
      </div>
      <div class="status-right">
        <el-select
          v-model="selectedSatellite"
          placeholder="选择卫星"
          size="default"
          style="width: 180px"
          @change="onSatelliteChange"
        >
          <el-option
            v-for="s in satellites"
            :key="s.id"
            :label="s.name || s.satellite_name"
            :value="s.id"
          />
        </el-select>
        <el-button type="primary" @click="startSSE" :loading="store.connecting" :disabled="!selectedSatellite">
          开始
        </el-button>
        <el-button type="danger" @click="stopSSE" :disabled="!store.connected && !store.connecting">
          停止
        </el-button>
        <el-button @click="showFrameDrawer = true">查看整帧</el-button>
        <el-button @click="store.resetCounters()">重置计数</el-button>
      </div>
    </div>

    <div class="realtime-body">
      <div class="tree-panel">
        <el-input
          v-model="treeFilter"
          placeholder="搜索参数..."
          size="small"
          clearable
          class="tree-filter"
        />
        <el-tree
          ref="treeRef"
          :data="filteredParamTree"
          show-checkbox
          node-key="code"
          :props="treeProps"
          :filter-node-method="filterNode"
          @check="onTreeCheck"
          default-expand-all
          size="small"
          class="param-tree"
        >
          <template #default="{ data }">
            <div class="tree-node">
              <template v-if="data.type === 'group'">
                <span class="node-group-label">{{ data.label }}</span>
                <el-tag
                  v-if="data.alarmedCount > 0"
                  type="danger"
                  size="small"
                  class="node-badge"
                >{{ data.alarmedCount }} 告警</el-tag>
                <el-tag type="info" size="small" class="node-badge">{{ data.total }} 项</el-tag>
              </template>
              <template v-else>
                <span
                  class="node-name"
                  :title="paramTip(data)"
                >{{ data.name || data.code }}</span>
                <span class="node-code">{{ data.code }}</span>
                <span class="node-value" :class="{ 'alarm-value': isAlarmed(data.code) }">
                  <template v-if="latestOf(data.code)">
                    {{ displayMode === 'value' ? latestOf(data.code).value : latestOf(data.code).raw_value }}
                    <span v-if="displayMode === 'value' && data.unit" class="unit">{{ data.unit }}</span>
                  </template>
                  <span v-else>-</span>
                </span>
              </template>
            </div>
          </template>
        </el-tree>
      </div>

      <div class="table-panel">
        <div class="table-toolbar">
          <span class="selected-count">已选 {{ selectedParamCodes.length }} 个参数</span>
          <el-radio-group v-model="displayMode" size="small">
            <el-radio-button value="value">工程值</el-radio-button>
            <el-radio-button value="raw">源码</el-radio-button>
          </el-radio-group>
        </div>
        <el-table
          :data="tableData"
          v-loading="store.connecting"
          height="calc(100vh - 280px)"
          stripe
          size="small"
          :row-class-name="tableRowClassName"
        >
          <el-table-column prop="param_code" label="参数代号" width="130" fixed />
          <el-table-column prop="name" label="名称" width="150" show-overflow-tooltip />
          <el-table-column :label="displayMode === 'value' ? '工程值' : '源码'" width="120">
            <template #default="{ row }">
              <span :class="{ 'alarm-value': row._alarm }">
                {{ displayMode === 'value' ? (row.value ?? row.raw_value ?? '-') : (row.raw_value ?? '-') }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="unit" label="单位" width="80" />
          <el-table-column label="源码" width="120" v-if="displayMode === 'value'">
            <template #default="{ row }">
              <span :class="{ 'alarm-value': row._alarm }">{{ row.raw_value ?? '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="quality" label="质量" width="80">
            <template #default="{ row }">
              <el-tag :type="qualityType(row.quality)" size="small">{{ row.quality || '-' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="更新时间" width="170">
            <template #default="{ row }">
              {{ row._ts ? dayjs(row._ts).format('YYYY-MM-DD HH:mm:ss') : '-' }}
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <el-drawer v-model="showFrameDrawer" title="最新帧" size="620px" direction="rtl">
      <template v-if="store.recentFrames.length">
        <div class="frame-selector">
          <el-select v-model="selectedFrameIndex" placeholder="选择帧" size="small" style="width: 100%">
            <el-option
              v-for="(f, i) in store.recentFrames"
              :key="i"
              :label="`帧 #${store.recentFrames.length - i} — ${formatFrameTime(f)} (${f.protocol_type || '未知'})`"
              :value="i"
            />
          </el-select>
        </div>
        <el-tabs v-model="frameTab" class="frame-tabs">
          <el-tab-pane label="十六进制" name="hex">
            <div class="frame-hex">
              <pre>{{ formatFrameHex(store.recentFrames[selectedFrameIndex]) }}</pre>
            </div>
          </el-tab-pane>
          <el-tab-pane label="解析详情" name="parse">
            <div class="parse-toolbar">
              <el-button
                type="primary"
                size="small"
                :loading="parsingFrame"
                @click="parseSelectedFrame"
              >解析当前帧</el-button>
              <el-tag v-if="parseResult" :type="parseResult.ok ? 'success' : 'danger'" size="small">
                {{ parseResult.ok ? '解析通过' : (parseResult.message || '解析失败') }}
              </el-tag>
            </div>
            <el-table
              v-if="parseResult && parseResult.fields && parseResult.fields.length"
              :data="parseResult.fields"
              size="small"
              border
              max-height="52vh"
            >
              <el-table-column prop="name" label="字段" width="170" />
              <el-table-column prop="value" label="值" show-overflow-tooltip />
              <el-table-column prop="desc" label="说明" show-overflow-tooltip />
            </el-table>
            <el-empty v-else-if="!parsingFrame" description="点击「解析当前帧」查看结构化字段" />
          </el-tab-pane>
        </el-tabs>
      </template>
      <el-empty v-else description="暂无帧数据" />
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import { useTelemetryStore } from '../stores/telemetry'
import { satelliteApi, paramApi, channelApi } from '../api/satellite'
import { telemetryApi } from '../api/telemetry'

const store = useTelemetryStore()

const satellites = ref([])
const params = ref([])
const selectedSatellite = ref(null)
const treeRef = ref(null)
const treeFilter = ref('')
const showFrameDrawer = ref(false)
const selectedFrameIndex = ref(0)
const displayMode = ref('value')
const frameTab = ref('hex')
const parseResult = ref(null)
const parsingFrame = ref(false)

const selectedParamCodes = ref([])
const paramMetaMap = reactive({})

const treeProps = {
  children: 'children',
  label: 'label'
}

const statusTagType = computed(() => {
  if (store.connecting) return 'warning'
  if (store.connected) return 'success'
  return 'danger'
})

const statusText = computed(() => {
  if (store.connecting) return '连接中...'
  if (store.connected) return '已连接'
  return '未连接'
})

const paramTree = computed(() => {
  const groups = {}
  params.value.forEach((p) => {
    const code = p.code || p.param_code
    const subsystem = p.subsystem || p.subsystem_name || p.group || '未分组'
    if (!groups[subsystem]) {
      groups[subsystem] = { id: subsystem, label: subsystem, type: 'group', children: [] }
    }
    groups[subsystem].children.push({
      id: code,
      code: code,
      type: 'param',
      label: `${code} - ${p.name || code}`,
      name: p.name || code,
      unit: p.unit || '',
      description: p.description || '',
      data_type: p.data_type || 'float',
      threshold_min: p.threshold_min ?? null,
      threshold_max: p.threshold_max ?? null,
      subsystem: subsystem
    })
  })
  return Object.values(groups).map((g) => {
    g.total = g.children.length
    g.alarmedCount = g.children.filter((c) => !!store.alarmedParams[c.code]).length
    return g
  })
})

const filteredParamTree = computed(() => {
  if (!treeFilter.value) return paramTree.value
  const filter = treeFilter.value.toLowerCase()
  return paramTree.value
    .map((group) => ({
      ...group,
      children: (group.children || []).filter(
        (c) => c.label.toLowerCase().includes(filter) || c.code.toLowerCase().includes(filter)
      )
    }))
    .filter((g) => g.children && g.children.length > 0)
})

function latestOf(code) {
  return store.latestValues[code] || null
}

function isAlarmed(code) {
  return !!store.alarmedParams[code]
}

function paramTip(node) {
  const parts = [
    node.name,
    node.description ? `描述: ${node.description}` : '',
    `类型: ${node.data_type}`,
    node.unit ? `单位: ${node.unit}` : '',
    `阈值: ${node.threshold_min ?? '-'} ~ ${node.threshold_max ?? '-'}`,
    `分系统: ${node.subsystem}`
  ]
  return parts.filter(Boolean).join('\n')
}

const tableData = computed(() => {
  return selectedParamCodes.value
    .map((code) => {
      const latest = store.latestValues[code]
      const meta = paramMetaMap[code] || {}
      const alarmed = !!store.alarmedParams[code]
      return {
        param_code: code,
        name: meta.name || code,
        value: latest?.value,
        raw_value: latest?.raw_value,
        unit: latest?.unit || meta.unit || '',
        quality: latest?.quality,
        _ts: latest?._ts || null,
        _alarm: alarmed
      }
    })
})

function tableRowClassName({ row }) {
  return row._alarm ? 'alarm-row' : ''
}

function qualityType(quality) {
  if (!quality) return 'info'
  const q = String(quality).toLowerCase()
  if (q === 'good' || q === 'valid' || q === '正常') return 'success'
  if (q === 'warning' || q === 'caution') return 'warning'
  if (q === 'bad' || q === 'invalid' || q === '异常') return 'danger'
  return 'info'
}

function filterNode(value, data) {
  if (!value) return true
  return data.label.toLowerCase().includes(value.toLowerCase())
}

function onTreeCheck(_node, checked) {
  const allChecked = [
    ...checked.checkedNodes.map((n) => n.code),
    ...checked.halfCheckedNodes.map((n) => n.code)
  ]
  selectedParamCodes.value = allChecked.filter(Boolean)
}

async function loadSatellites() {
  try {
    const res = await satelliteApi.list()
    satellites.value = Array.isArray(res) ? res : (res.items || res.data || [])
  } catch {
    satellites.value = []
  }
}

async function loadParams() {
  if (!selectedSatellite.value) return
  try {
    const res = await paramApi.list({ satellite_id: selectedSatellite.value })
    params.value = Array.isArray(res) ? res : (res.items || res.data || [])
    params.value.forEach((p) => {
      const code = p.code || p.param_code
      if (code) {
        paramMetaMap[code] = {
          name: p.name || code,
          unit: p.unit || '',
          subsystem: p.subsystem || p.subsystem_name || p.group || '未分组'
        }
      }
    })
    await nextTick()
    restoreCheckedParams()
  } catch {
    params.value = []
  }
}

function restoreCheckedParams() {
  if (!treeRef.value) return
  const checkedKeys = selectedParamCodes.value.slice()
  treeRef.value.setCheckedKeys(checkedKeys, false)
}

function onSatelliteChange() {
  selectedParamCodes.value = []
  params.value = []
  store.disconnect()
  loadParams()
}

function startSSE() {
  if (!selectedSatellite.value) {
    ElMessage.warning('请先选择卫星')
    return
  }
  store.connect(selectedSatellite.value)
}

function stopSSE() {
  store.disconnect()
}

function formatFrameTime(frame) {
  if (!frame) return ''
  const ts = frame.ts || frame.received_at || frame.timestamp
  return ts ? dayjs(ts).format('HH:mm:ss.SSS') : ''
}

function formatFrameHex(frame) {
  if (!frame) return '无数据'
  if (frame.hex) return frame.hex
  if (frame.data && typeof frame.data === 'string') return frame.data
  try {
    return JSON.stringify(frame, null, 2)
  } catch {
    return String(frame)
  }
}

async function parseSelectedFrame() {
  const frame = store.recentFrames[selectedFrameIndex.value]
  if (!frame) return
  const rawHex = frame.raw_hex || frame.hex || frame.rawHex || frame.data
  if (!rawHex) {
    ElMessage.warning('该帧无十六进制数据')
    return
  }
  parsingFrame.value = true
  parseResult.value = null
  try {
    const res = await telemetryApi.parseFrame({
      protocol_type: frame.protocol_type || 'CCSDS',
      hex_data: typeof rawHex === 'string' ? rawHex : ''
    })
    parseResult.value = res
  } catch {
    ElMessage.error('解析失败，请检查协议类型与帧格式')
  } finally {
    parsingFrame.value = false
  }
}

watch(selectedFrameIndex, () => {
  showFrameDrawer.value = true
})

watch(showFrameDrawer, (val) => {
  if (val) {
    selectedFrameIndex.value = 0
  }
})

onMounted(() => {
  loadSatellites()
})

onBeforeUnmount(() => {
  store.disconnect()
})
</script>

<style scoped>
.realtime-page {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  background: #fff;
  border-radius: 6px;
  margin-bottom: 12px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  flex-wrap: wrap;
  gap: 8px;
}

.status-left {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: #666;
}

.stat-item b {
  color: #1a1a2e;
}

.status-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.realtime-body {
  flex: 1;
  display: flex;
  gap: 12px;
  min-height: 0;
}

.tree-panel {
  width: 340px;
  min-width: 340px;
  background: #fff;
  border-radius: 6px;
  padding: 12px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.tree-filter {
  margin-bottom: 8px;
}

.tree-panel :deep(.el-tree) {
  flex: 1;
  overflow-y: auto;
}

.tree-panel :deep(.el-tree-node__content) {
  height: 28px;
}

.tree-node {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 0;
  padding-right: 6px;
  font-size: 12px;
}

.node-group-label {
  font-weight: 500;
  color: #1a1a2e;
}

.node-badge {
  margin-left: 6px;
}

.node-name {
  flex: 0 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #333;
}

.node-code {
  color: #aaa;
  font-size: 11px;
  margin-left: 6px;
  flex-shrink: 0;
}

.node-value {
  margin-left: auto;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  color: #1a1a2e;
  padding-left: 8px;
  flex-shrink: 0;
}

.node-value .unit {
  color: #999;
  font-weight: 400;
  margin-left: 2px;
  font-size: 11px;
}

.alarm-value {
  color: #f56c6c;
  font-weight: 700;
}

.table-panel {
  flex: 1;
  background: #fff;
  border-radius: 6px;
  padding: 12px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.selected-count {
  font-size: 13px;
  color: #999;
}

.alarm-value {
  color: #f56c6c;
  font-weight: 700;
}

.frame-selector {
  margin-bottom: 12px;
}

.frame-tabs {
  margin-top: 4px;
}

.parse-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.frame-hex {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 16px;
  border-radius: 6px;
  overflow: auto;
  max-height: calc(100vh - 200px);
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  line-height: 1.6;
}

.frame-hex pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}

:deep(.alarm-row) {
  background-color: #fef0f0 !important;
}

:deep(.alarm-row:hover > td) {
  background-color: #fde2e2 !important;
}
</style>
