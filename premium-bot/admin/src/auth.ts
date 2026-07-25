import { computed, reactive } from 'vue'
import { api } from './api'

interface AuthState {
  token: string | null
  user: null | {
    id: string
    username: string
    role: string
  }
}

const state = reactive<AuthState>({
  token: localStorage.getItem('access_token'),
  user: null,
})

export const auth = {
  state,
  isLoggedIn: computed(() => Boolean(state.token)),
  async login(username: string, password: string) {
    const { data } = await api.post('/auth/login', { username, password })
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('refresh_token', data.refresh_token)
    state.token = data.access_token
    await this.me()
  },
  async me() {
    const { data } = await api.get('/auth/me')
    state.user = data
    return data
  },
  logout() {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    state.token = null
    state.user = null
  },
}
