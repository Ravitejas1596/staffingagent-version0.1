import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    rules: {
      // Block accidental imports of fixture/mock data from application code.
      // Fixtures may only be imported by test files or from within __fixtures__ itself.
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['**/__fixtures__/**', '**/data/mockData', '**/data/mockData.ts'],
              message:
                'Mock/fixture data must not be imported from application code. Move to tests or use real API endpoints.',
            },
          ],
        },
      ],
    },
  },
  {
    // Allow fixtures to self-import and allow tests to import fixtures.
    files: [
      'src/data/__fixtures__/**/*.{ts,tsx}',
      '**/*.test.{ts,tsx}',
      '**/*.spec.{ts,tsx}',
      'src/**/__tests__/**/*.{ts,tsx}',
    ],
    rules: {
      'no-restricted-imports': 'off',
    },
  },
])
