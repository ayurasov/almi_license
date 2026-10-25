// RFC 9457 problem+json of the server (infra/problems.py): the console relies on `code`,
// shows `user_message` as is and puts `data.fields` next to form fields.

export interface Problem {
  type: string
  title: string
  status: number
  code: string
  detail?: string
  request_id?: string
  user_message?: Record<string, string>
  data?: { fields?: Record<string, string[]> } & Record<string, unknown>
}

export class ApiError extends Error {
  readonly problem: Problem

  constructor(problem: Problem) {
    super(problem.detail ?? problem.title)
    this.name = 'ApiError'
    this.problem = problem
  }

  get fieldErrors(): Record<string, string[]> {
    return this.problem.data?.fields ?? {}
  }

  get hasFieldErrors(): boolean {
    return Object.keys(this.fieldErrors).length > 0
  }
}

/** The server could not be reached or answered without a problem document. */
export class NetworkError extends Error {
  constructor(message = 'network') {
    super(message)
    this.name = 'NetworkError'
  }
}

export function isProblem(value: unknown): value is Problem {
  if (typeof value !== 'object' || value === null) return false
  const candidate = value as Record<string, unknown>
  return typeof candidate.code === 'string' && typeof candidate.status === 'number'
}

export function userMessage(problem: Problem, locale: string): string | undefined {
  return problem.user_message?.[locale] ?? problem.user_message?.ru
}
