import http from './request'

export const userApi = {
  list: (params) => http.get('/system/users', { params }).then((r) => r.data),
  get: (id) => http.get(`/system/users/${id}`).then((r) => r.data),
  create: (data) => http.post('/system/users', data).then((r) => r.data),
  update: (id, data) => http.put(`/system/users/${id}`, data).then((r) => r.data),
  remove: (id) => http.delete(`/system/users/${id}`).then((r) => r.data)
}

export const roleApi = {
  list: () => http.get('/system/roles').then((r) => r.data),
  update: (name, data) => http.put(`/system/roles/${name}`, data).then((r) => r.data)
}

export const logApi = {
  list: (params) => http.get('/system/logs', { params }).then((r) => r.data),
  stats: () => http.get('/system/logs/stats').then((r) => r.data)
}

export const timeApi = {
  current: () => http.get('/system/time').then((r) => r.data)
}
