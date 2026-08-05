import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '../api/auth'

const STORAGE_KEY_PREFIX = 'stms_'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem(`${STORAGE_KEY_PREFIX}token`) || '')
  const refreshToken = ref(localStorage.getItem(`${STORAGE_KEY_PREFIX}refresh_token`) || '')
  const user = ref(loadUser())

  function loadUser() {
    try {
      const raw = localStorage.getItem(`${STORAGE_KEY_PREFIX}user`)
      return raw ? JSON.parse(raw) : null
    } catch {
      return null
    }
  }

  function saveToken(access, refresh) {
    token.value = access
    refreshToken.value = refresh
    localStorage.setItem(`${STORAGE_KEY_PREFIX}token`, access)
    localStorage.setItem(`${STORAGE_KEY_PREFIX}refresh_token`, refresh)
  }

  function saveUser(u) {
    user.value = u
    localStorage.setItem(`${STORAGE_KEY_PREFIX}user`, JSON.stringify(u))
  }

  const isLoggedIn = computed(() => !!token.value)
  const role = computed(() => user.value?.role || 'observer')

  async function login(credentials) {
    const res = await authApi.login(credentials)
    saveToken(res.access_token, res.refresh_token)
    saveUser(res.user)
  }

  async function register(data) {
    await authApi.register(data)
  }

  async function fetchMe() {
    const res = await authApi.me()
    saveUser(res)
  }

  async function changePassword(data) {
    await authApi.changePassword(data)
  }

  function logout() {
    token.value = ''
    refreshToken.value = ''
    user.value = null
    localStorage.removeItem(`${STORAGE_KEY_PREFIX}token`)
    localStorage.removeItem(`${STORAGE_KEY_PREFIX}refresh_token`)
    localStorage.removeItem(`${STORAGE_KEY_PREFIX}user`)
  }

  return {
    token,
    refreshToken,
    user,
    isLoggedIn,
    role,
    login,
    register,
    fetchMe,
    changePassword,
    logout,
    saveToken
  }
})
