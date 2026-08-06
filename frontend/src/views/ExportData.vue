<template>
  <div class="export-page">
    <div class="page-header">
      <h3 class="page-title">数据导出</h3>
      <p class="page-desc">导出遥测数据到本地文件</p>
    </div>

    <el-card shadow="never">
      <el-form :model="form" label-width="100px" size="default">
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="form.timeRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            value-format="YYYY-MM-DD HH:mm:ss"
            style="width: 420px"
          />
        </el-form-item>

        <el-form-item label="遥测参数">
          <el-select
            v-model="form.paramCodes"
            multiple
            filterable
            placeholder="请选择参数（可多选）"
            style="width: 420px"
            collapse-tags
            collapse-tags-tooltip
          >
            <el-option
              v-for="p in paramList"
              :key="p.id"
              :label="p.param_code + ' (' + (p.param_name || p.param_code) + ')'"
              :value="p.param_code"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="通道">
          <el-select
            v-model="form.channelIds"
            multiple
            filterable
            placeholder="请选择通道（可选，不选则导出全部）"
            style="width: 420px"
            collapse-tags
            collapse-tags-tooltip
          >
            <el-option
              v-for="c in channelList"
              :key="c.id"
              :label="c.channel_name || c.name || ('通道-' + c.id)"
              :value="c.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="导出格式">
          <el-radio-group v-model="form.format">
            <el-radio-button value="csv">CSV</el-radio-button>
            <el-radio-button value="excel">Excel</el-radio-button>
            <el-radio-button value="json">JSON</el-radio-button>
            <el-radio-button value="txt">TXT</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="exportLoading" @click="doExport">
            <el-icon style="margin-right: 4px"><Download /></el-icon>
            导出数据
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import { paramApi, channelApi } from '../api/satellite'
import { exportApi } from '../api/telemetry'

const paramList = ref([])
const channelList = ref([])
const exportLoading = ref(false)

const form = reactive({
  timeRange: [],
  paramCodes: [],
  channelIds: [],
  format: 'csv'
})

const formatMap = {
  csv: { api: exportApi.csv, ext: 'csv' },
  excel: { api: exportApi.excel, ext: 'xlsx' },
  json: { api: exportApi.json, ext: 'json' },
  txt: { api: exportApi.txt, ext: 'txt' }
}

async function fetchOptions() {
  try {
    const [params, channels] = await Promise.allSettled([
      paramApi.list({ limit: 200 }),
      channelApi.list({ limit: 200 })
    ])
    if (params.status === 'fulfilled') {
      const d = params.value
      paramList.value = Array.isArray(d) ? d : (d.items || [])
    }
    if (channels.status === 'fulfilled') {
      const d = channels.value
      channelList.value = Array.isArray(d) ? d : (d.items || [])
    }
  } catch {}
}

async function doExport() {
  if (!form.timeRange?.length) {
    ElMessage.warning('请选择时间范围')
    return
  }
  if (!form.paramCodes.length) {
    ElMessage.warning('请至少选择一个遥测参数')
    return
  }
  exportLoading.value = true
  try {
    const [start, end] = form.timeRange
    const cfg = formatMap[form.format]
    const params = {
      start,
      end,
      param_codes: form.paramCodes
    }
    if (form.channelIds.length) {
      params.channel_ids = form.channelIds
    }
    const blob = await cfg.api(params)
    const url = window.URL.createObjectURL(new Blob([blob]))
    const a = document.createElement('a')
    a.href = url
    a.download = `遥测数据导出_${dayjs().format('YYYYMMDD_HHmmss')}.${cfg.ext}`
    a.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success('数据导出成功')
  } catch {} finally {
    exportLoading.value = false
  }
}

onMounted(fetchOptions)
</script>

<style scoped>
.export-page { }
.page-header { margin-bottom: 16px; }
.page-title { margin: 0 0 4px; font-size: 20px; color: #1a1a2e; }
.page-desc { margin: 0; color: #999; font-size: 14px; }
</style>
