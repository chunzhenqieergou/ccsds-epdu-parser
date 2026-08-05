import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'

export const useTelemetryStore = defineStore('telemetry', () => {
  const connected = ref(false)
  const latestValues = reactive({})
  const frameCount = ref(0)
  const errorCount = ref(0)
  const recentFrames = ref([])
  const alarms = ref([])
  const alarmedParams = reactive({})
  const lastHeartbeat = ref(null)
  const connecting = ref(false)

  let eventSource = null
  let reconnectTimer = null
  let heartbeatTimer = null
  let reconnectDelay = 3000
  let pendingSatelliteId = null

  function startHeartbeat() {
    stopHeartbeat()
    lastHeartbeat.value = Date.now()
    heartbeatTimer = setInterval(() => {
      lastHeartbeat.value = Date.now()
    }, 10000)
  }

  function stopHeartbeat() {
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
  }

  function connect(satelliteId = null) {
    disconnect()
    connecting.value = true
    pendingSatelliteId = satelliteId
    reconnectDelay = 3000

    const params = new URLSearchParams()
    if (satelliteId) params.set('satellite_id', satelliteId)
    const token = localStorage.getItem('stms_token') || ''
    params.set('token', token)

    const url = `/api/v1/telemetry/sse?${params.toString()}`
    eventSource = new EventSource(url)

    eventSource.onopen = () => {
      connected.value = true
      connecting.value = false
      reconnectDelay = 3000
      startHeartbeat()
    }

    eventSource.addEventListener('realtime_point', (e) => {
      try {
        const point = JSON.parse(e.data)
        latestValues[point.param_code] = {
          ...(latestValues[point.param_code] || {}),
          ...point,
          _ts: Date.now()
        }
        frameCount.value++
      } catch {
        errorCount.value++
      }
    })

    eventSource.addEventListener('telemetry', (e) => {
      try {
        const point = JSON.parse(e.data)
        latestValues[point.param_code] = {
          ...(latestValues[point.param_code] || {}),
          ...point,
          _ts: Date.now()
        }
        frameCount.value++
      } catch {
        errorCount.value++
      }
    })

    eventSource.addEventListener('frame', (e) => {
      try {
        const frame = JSON.parse(e.data)
        recentFrames.value.unshift(frame)
        if (recentFrames.value.length > 50) {
          recentFrames.value.pop()
        }
      } catch {
        errorCount.value++
      }
    })

    eventSource.addEventListener('alarm', (e) => {
      try {
        const alarm = JSON.parse(e.data)
        alarms.value.unshift(alarm)
        if (alarms.value.length > 100) {
          alarms.value.pop()
        }
        if (alarm.param_code) {
          alarmedParams[alarm.param_code] = alarm
        }
      } catch {
        errorCount.value++
      }
    })

    eventSource.onerror = () => {
      connected.value = false
      connecting.value = false
      errorCount.value++
      stopHeartbeat()
      disconnect()
      scheduleReconnect()
    }
  }

  function scheduleReconnect() {
    if (reconnectTimer) return
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      if (!connected.value && pendingSatelliteId !== null) {
        reconnectDelay = Math.min(reconnectDelay * 1.5, 30000)
        connect(pendingSatelliteId)
      }
    }, reconnectDelay)
  }

  function disconnect() {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    stopHeartbeat()
    connected.value = false
    connecting.value = false
    pendingSatelliteId = null
  }

  function getValue(paramCode) {
    return latestValues[paramCode] || null
  }

  function resetCounters() {
    frameCount.value = 0
    errorCount.value = 0
  }

  function clearAlarms() {
    alarms.value = []
    Object.keys(alarmedParams).forEach((k) => delete alarmedParams[k])
  }

  return {
    connected,
    connecting,
    latestValues,
    frameCount,
    errorCount,
    recentFrames,
    alarms,
    alarmedParams,
    lastHeartbeat,
    connect,
    disconnect,
    getValue,
    resetCounters,
    clearAlarms
  }
})
