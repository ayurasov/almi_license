import 'primeicons/primeicons.css'

import Aura from '@primeuix/themes/aura'
import { createPinia } from 'pinia'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import { createApp } from 'vue'

import App from './App.vue'
import { i18n } from './i18n'
import { router } from './router'

createApp(App)
  .use(createPinia())
  .use(i18n)
  .use(router)
  .use(PrimeVue, { theme: { preset: Aura, options: { darkModeSelector: '.app-dark' } } })
  .use(ToastService)
  .mount('#app')
