import { createI18n } from 'vue-i18n'

import en from './en'
import ru from './ru'

export const i18n = createI18n({
  legacy: false,
  locale: 'ru',
  fallbackLocale: 'ru',
  messages: { ru, en },
  // 'long': date and time to the second (journal, E10-04); 'short': the date only
  datetimeFormats: {
    ru: { long: { dateStyle: 'short', timeStyle: 'medium' }, short: { dateStyle: 'short' } },
    en: { long: { dateStyle: 'short', timeStyle: 'medium' }, short: { dateStyle: 'short' } },
  },
})
