import { execFileSync } from 'node:child_process'
import { randomBytes } from 'node:crypto'

// Accounts of this run; their passwords exist only in the environment of the run.
export default function globalSetup(): void {
  const env = { ...process.env, DJANGO_SETTINGS_MODULE: 'almi_license.settings.dev', DEPLOYMENT_MODE: 'central' }
  execFileSync('uv', ['run', 'python', 'manage.py', 'migrate', '--noinput'], { cwd: '../server', env, stdio: 'ignore' })
  execFileSync('uv', ['run', 'python', 'manage.py', 'loadcatalog'], { cwd: '../server', env, stdio: 'ignore' })
  // An operator for most scenarios and an administrator for the Users screen (E07-09).
  for (const role of ['operator', 'admin'] as const) {
    const username = `e2e-${role}-${randomBytes(4).toString('hex')}`
    const password = randomBytes(18).toString('base64url')
    execFileSync('uv', ['run', 'python', 'manage.py', 'create_account', '--username', username, '--role', role], {
      cwd: '../server',
      env: { ...env, CONSOLE_PASSWORD: password },
      stdio: 'ignore',
    })
    const prefix = role === 'operator' ? 'E2E' : 'E2E_ADMIN'
    process.env[`${prefix}_USERNAME`] = username
    process.env[`${prefix}_PASSWORD`] = password
  }
}
