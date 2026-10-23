import { defineConfigWithVueTs, vueTsConfigs } from '@vue/eslint-config-typescript'
import pluginVue from 'eslint-plugin-vue'

export default defineConfigWithVueTs(
  { ignores: ['dist/**', 'node_modules/**', 'src/api/generated/**', 'playwright-report/**', 'test-results/**'] },
  pluginVue.configs['flat/recommended'],
  vueTsConfigs.strictTypeChecked,
  {
    rules: {
      // Texts come only from i18n (AGENTS.md, rule 14).
      'vue/no-bare-strings-in-template': ['error', { allowlist: ['—', '·', ':', '(', ')', '/'] }],
      'vue/multi-word-component-names': 'off',
    },
  },
)
