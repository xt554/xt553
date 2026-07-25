import { createRouter, createWebHistory } from 'vue-router'
import { auth } from './auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: () => import('./views/LoginView.vue') },
    {
      path: '/',
      component: () => import('./layouts/AdminLayout.vue'),
      children: [
        { path: '', name: 'dashboard', component: () => import('./views/DashboardView.vue') },
        { path: 'users', name: 'users', component: () => import('./views/UsersView.vue') },
        { path: 'orders', name: 'orders', component: () => import('./views/OrdersView.vue') },
        { path: 'plans', name: 'plans', component: () => import('./views/PlansView.vue') },
        { path: 'wallet-accounts', name: 'wallet-accounts', component: () => import('./views/WalletAccountsView.vue') },
        { path: 'wallets', name: 'wallets', component: () => import('./views/WalletsView.vue') },
        { path: 'logs', name: 'logs', component: () => import('./views/LogsView.vue') },
        { path: 'fragment-runners', name: 'fragment-runners', component: () => import('./views/FragmentRunnersView.vue') },
        { path: 'settings', name: 'settings', component: () => import('./views/SettingsView.vue') },
      ],
    },
  ],
})

router.beforeEach((to) => {
  if (to.path !== '/login' && !auth.isLoggedIn.value) return '/login'
  if (to.path === '/login' && auth.isLoggedIn.value) return '/'
})

export default router
