// Form validation of a customer (zod); messages are i18n keys, the form translates them.
import { z } from 'zod'

import { innIsValid } from './inn'

export const customerSchema = z.object({
  name: z.string().trim().min(1, 'customers.errors.nameRequired').max(512),
  inn: z
    .string()
    .trim()
    .refine((value) => value === '' || innIsValid(value), 'customers.errors.innInvalid'),
  external_id: z.string().trim().max(128),
  status: z.enum(['active', 'archived']),
})

export type CustomerForm = z.infer<typeof customerSchema>

/** zod issues as field -> message keys, the same shape as server field errors. */
export function formErrors(values: unknown): Record<string, string[]> {
  const result = customerSchema.safeParse(values)
  if (result.success) return {}
  const errors: Record<string, string[]> = {}
  for (const issue of result.error.issues) {
    const field = String(issue.path[0] ?? 'form')
    ;(errors[field] ??= []).push(issue.message)
  }
  return errors
}
