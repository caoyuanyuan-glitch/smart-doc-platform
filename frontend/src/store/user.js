import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useUserStore = defineStore('user', () => {
  function readLocalStorage(key, fallback = '') {
    try {
      return localStorage.getItem(key) || fallback
    } catch {
      return fallback
    }
  }

  function readStoredUser() {
    const raw = readLocalStorage('user', 'null')
    try {
      return JSON.parse(raw)
    } catch {
      localStorage.removeItem('user')
      return null
    }
  }

  const token = ref(readLocalStorage('token'))
  const user = ref(readStoredUser())

  const isAdmin = computed(() => user.value?.role === 'admin')
  const isLoggedIn = computed(() => !!token.value)

  function setToken(newToken) {
    token.value = newToken
    localStorage.setItem('token', newToken)
  }

  function setUser(newUser) {
    user.value = newUser
    localStorage.setItem('user', JSON.stringify(newUser))
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }

  return { token, user, isAdmin, isLoggedIn, setToken, setUser, logout }
})
