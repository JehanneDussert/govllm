// SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
// SPDX-License-Identifier: EUPL-1.2

export function scoreClass(score: number | null): string {
  if (score === null) return ''
  if (score >= 0.7) return 'green'
  if (score >= 0.4) return 'yellow'
  return 'red'
}
