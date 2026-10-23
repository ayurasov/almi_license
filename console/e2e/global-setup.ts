import { execFileSync } from 'node:child_process'
import { randomBytes } from 'node:crypto'

// The operator of this run; the password exists only in the environment of the run.
export default function globalSetup(): void {
  const username = `e2e-${randomBytes(4).toString('hex')}`
  const password = randomBytes(18).toString('base64url')
  const env = { ...process.env, DJANGO_SETTINGS_MODULE: 'almi_license.settings.dev', DEPLOYMENT_MODE: 'central' }
  execFileSync('uv', ['run', 'python', 'manage.py', 'migrate', '--noinput'], { cwd: '../server', env, stdio: 'ignore' })
  execFileSync('uv', ['run', 'python', 'manage.py', 'create_account', '--username', username, '--role', 'operator'], {
    cwd: '../server',
    env: { ...env, CONSOLE_PASSWORD: password },
    stdio: 'ignore',
  })
  process.env.E2E_USERNAME = username
  process.env.E2E_PASSWORD = password
}
