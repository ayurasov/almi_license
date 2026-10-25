// Preview of profile messages (E07-06): the product fills the substitutions itself
// (section 9 of document 2), the console shows them with sample values of the license card.
export const SUBSTITUTIONS = [
  'days_left',
  'valid_until',
  'customer',
  'used',
  'limit',
  'product',
  'support_contact',
] as const

export type Substitution = (typeof SUBSTITUTIONS)[number]
export type Sample = Record<Substitution, string>

const PLACEHOLDER = /\{([^{}]*)\}/g

export function unknownSubstitutions(text: string): string[] {
  const known = new Set<string>(SUBSTITUTIONS)
  const found = [...text.matchAll(PLACEHOLDER)].map((match) => match[1] ?? '')
  return [...new Set(found.filter((name) => !known.has(name)))].sort()
}

export function preview(text: string, sample: Sample): string {
  return text.replace(PLACEHOLDER, (whole, name: string) =>
    (SUBSTITUTIONS as readonly string[]).includes(name) ? sample[name as Substitution] : whole,
  )
}
