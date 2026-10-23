// INN check digits — the same rule as the server (apps/licensing/domain/inn.py).
const W10 = [2, 4, 10, 3, 5, 9, 4, 6, 8]
const W11 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
const W12 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]

function checkDigit(digits: number[], weights: number[]): number {
  return (weights.reduce((sum, weight, i) => sum + weight * (digits[i] ?? 0), 0) % 11) % 10
}

export function innIsValid(inn: string): boolean {
  if (!/^(\d{10}|\d{12})$/.test(inn)) return false
  const digits = Array.from({ length: inn.length }, (_, i) => Number(inn.charAt(i)))
  if (digits.length === 10) return checkDigit(digits, W10) === digits[9]
  return checkDigit(digits, W11) === digits[10] && checkDigit(digits, W12) === digits[11]
}
