import http from './request'

export const telemetryApi = {
  query: (params) => http.get('/telemetry/query', { params }).then((r) => r.data),
  latest: (params) => http.get('/telemetry/latest', { params }).then((r) => r.data),
  realtime: (params) => http.get('/telemetry/realtime', { params }).then((r) => r.data),
  frames: (params) => http.get('/telemetry/frames', { params }).then((r) => r.data),
  frame: (id) => http.get(`/telemetry/frames/${id}`).then((r) => r.data),
  parseFrame: (data) => http.post('/telemetry/parse-frame', data).then((r) => r.data)
}

export const statisticsApi = {
  basic: (params) => http.post('/statistics/basic', params).then((r) => r.data),
  trend: (params) => http.post('/statistics/trend', params).then((r) => r.data),
  compare: (params) => http.post('/statistics/compare', params).then((r) => r.data),
  anomaly: (params) => http.post('/statistics/anomaly', params).then((r) => r.data)
}

export const alarmApi = {
  list: (params) => http.get('/alarms', { params }).then((r) => r.data),
  get: (id) => http.get(`/alarms/${id}`).then((r) => r.data),
  handle: (id, data) => http.put(`/alarms/${id}/handle`, data).then((r) => r.data),
  remove: (id) => http.delete(`/alarms/${id}`).then((r) => r.data),
  stats: () => http.get('/alarms/stats').then((r) => r.data)
}

export const exportApi = {
  telemetry: (params) =>
    http.post('/export/telemetry', params, { responseType: 'blob' }).then((r) => r.data),
  excel: (params) =>
    http.post('/export/excel', params, { responseType: 'blob' }).then((r) => r.data),
  csv: (params) =>
    http.post('/export/csv', params, { responseType: 'blob' }).then((r) => r.data),
  json: (params) =>
    http.post('/export/json', params, { responseType: 'blob' }).then((r) => r.data),
  txt: (params) =>
    http.post('/export/txt', params, { responseType: 'blob' }).then((r) => r.data)
}
