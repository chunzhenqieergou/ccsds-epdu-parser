import { ref, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'

export function useEcharts(chartRef, initOption = null) {
  const chartInstance = ref(null)

  function initChart() {
    if (!chartRef.value) return
    const instance = echarts.init(chartRef.value)
    if (initOption) {
      instance.setOption(initOption)
    }
    chartInstance.value = instance
  }

  function setOption(option, notMerge = false) {
    chartInstance.value?.setOption(option, notMerge)
  }

  function getInstance() {
    return chartInstance.value
  }

  function resize() {
    chartInstance.value?.resize()
  }

  function dispose() {
    chartInstance.value?.dispose()
    chartInstance.value = null
  }

  let resizeObserver = null

  onMounted(() => {
    initChart()
    resizeObserver = new ResizeObserver(() => {
      resize()
    })
    if (chartRef.value) {
      resizeObserver.observe(chartRef.value)
    }
    window.addEventListener('resize', resize)
  })

  onUnmounted(() => {
    window.removeEventListener('resize', resize)
    resizeObserver?.disconnect()
    dispose()
  })

  return {
    chartInstance,
    initChart,
    setOption,
    getInstance,
    resize,
    dispose
  }
}
