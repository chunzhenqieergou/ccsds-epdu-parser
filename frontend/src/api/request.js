import axios from 'axios'
import { ElMessage } from 'element-plus'

const http = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
  paramsSerializer: {
    serialize(params) {
      const sp = new URLSearchParams()
      Object.entries(params).forEach(([key, value]) => {
        if (value === undefined || value === null) return
        if (Array.isArray(value)) {
          // 后端约定: param_codes 等数组参数用逗号分隔的字符串
          sp.append(key, value.join(','))
        } else {
          sp.append(key, value)
        }
      })
      return sp.toString()
    }
  }
})
let isRefreshing = false
let refreshSubscribers = []

function onRefreshed(newToken) {
  refreshSubscribers.forEach((cb) => cb(newToken))
  refreshSubscribers = []
}

function addRefreshSubscriber(cb) {
  refreshSubscribers.push(cb)
}

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('stms_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (response) => {
    // Blob 下载响应：保留原始 response，由调用方取 response.data（Blob）
    // 否则下面的解包会把 Blob 直接返回，导致 API 层 .then(r => r.data) 取到 undefined
    if (response.config.responseType === 'blob') {
      return response
    }
    const body = response.data
    if (body.code !== undefined && body.code !== 0) {
      ElMessage.error(body.message || '请求失败')
      return Promise.reject(new Error(body.message || '请求失败'))
    }
    return body
  },
  async (error) => {
    if (!error.response) {
      ElMessage.error('网络错误，请检查连接')
      return Promise.reject(error)
    }

    const { status, config } = error.response

    if (status === 401 && !config._retry) {
      const refreshToken = localStorage.getItem('stms_refresh_token')
      if (!refreshToken) {
        logoutAndRedirect()
        return Promise.reject(error)
      }

      if (isRefreshing) {
        return new Promise((resolve) => {
          addRefreshSubscriber((newToken) => {
            config.headers.Authorization = `Bearer ${newToken}`
            resolve(http(config))
          })
        })
      }

      config._retry = true
      isRefreshing = true

      try {
        const res = await axios.post('/api/v1/auth/refresh', { refresh_token: refreshToken })
        const newToken = res.data.data.access_token
        const newRefreshToken = res.data.data.refresh_token
        localStorage.setItem('stms_token', newToken)
        localStorage.setItem('stms_refresh_token', newRefreshToken)
        isRefreshing = false
        onRefreshed(newToken)
        config.headers.Authorization = `Bearer ${newToken}`
        return http(config)
      } catch {
        isRefreshing = false
        refreshSubscribers = []
        logoutAndRedirect()
        return Promise.reject(error)
      }
    }

    if (status !== 401) {
      const msg = error.response.data?.message || `服务器错误 (${status})`
      ElMessage.error(msg)
    }

    return Promise.reject(error)
  }
)

function logoutAndRedirect() {
  localStorage.removeItem('stms_token')
  localStorage.removeItem('stms_refresh_token')
  localStorage.removeItem('stms_user')
  window.location.href = '/login'
}

export default http
