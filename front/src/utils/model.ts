// SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
// SPDX-License-Identifier: EUPL-1.2

export function modelShortName(model: string): string {
  return model.split('/').pop() ?? model
}

export function shortModel(model: string | null): string | null {
  if (!model) return null
  return model.split('/').pop() ?? model
}
