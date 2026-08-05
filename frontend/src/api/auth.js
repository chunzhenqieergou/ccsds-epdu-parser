import http from './request'

export const authApi = {
  login: (data) => http.post('/auth/login', data).then((r) => r.data),
  register: (data) => http.post('/auth/register', data).then((r) => r.data),
  refresh: (data) => http.post('/auth/refresh', data).then((r) => r.data),
  me: () => http.get('/auth/me').then((r) => r.data),
  logout: () => http.post('/auth/logout').then((r) => r.data),
  changePassword: (data) => http.put('/auth/change-password', data).then((r) => r.data)
}
