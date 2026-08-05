import http from './request'

export const satelliteApi = {
  list: (params) => http.get('/satellites', { params }).then((r) => r.data),
  get: (id) => http.get(`/satellites/${id}`).then((r) => r.data),
  create: (data) => http.post('/satellites', data).then((r) => r.data),
  update: (id, data) => http.put(`/satellites/${id}`, data).then((r) => r.data),
  remove: (id) => http.delete(`/satellites/${id}`).then((r) => r.data)
}

export const paramApi = {
  list: (params) => http.get('/params', { params }).then((r) => r.data),
  tree: (params) => http.get('/params/tree', { params }).then((r) => r.data),
  get: (id) => http.get(`/params/${id}`).then((r) => r.data),
  create: (data) => http.post('/params', data).then((r) => r.data),
  update: (id, data) => http.put(`/params/${id}`, data).then((r) => r.data),
  remove: (id) => http.delete(`/params/${id}`).then((r) => r.data),
  importExcel: (satelliteId, file) => {
    const formData = new FormData()
    formData.append('file', file)
    return http.post(`/params/import/${satelliteId}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    }).then((r) => r.data)
  },
  exportExcel: (satelliteId) =>
    http.get(`/params/export/${satelliteId}`, { responseType: 'blob' }).then((r) => r.data)
}

export const channelApi = {
  list: (params) => http.get('/channels', { params }).then((r) => r.data),
  get: (id) => http.get(`/channels/${id}`).then((r) => r.data),
  create: (data) => http.post('/channels', data).then((r) => r.data),
  update: (id, data) => http.put(`/channels/${id}`, data).then((r) => r.data),
  remove: (id) => http.delete(`/channels/${id}`).then((r) => r.data),
  start: (id) => http.post(`/channels/${id}/start`).then((r) => r.data),
  stop: (id) => http.post(`/channels/${id}/stop`).then((r) => r.data)
}

export const commandApi = {
  list: (params) => http.get('/commands', { params }).then((r) => r.data),
  get: (id) => http.get(`/commands/${id}`).then((r) => r.data),
  create: (data) => http.post('/commands', data).then((r) => r.data),
  update: (id, data) => http.put(`/commands/${id}`, data).then((r) => r.data),
  remove: (id) => http.delete(`/commands/${id}`).then((r) => r.data),
  send: (id, params) => http.post(`/commands/${id}/send`, params).then((r) => r.data)
}
