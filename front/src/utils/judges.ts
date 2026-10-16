// SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
// SPDX-License-Identifier: EUPL-1.2

import type { JudgeConfig } from '@/api/client'

/**
 * Models that will actually judge an output under a given profile.
 *
 * Mirrors back/evaluation/jobs/eval_runner.py: if the profile has a panel with
 * members, each member judges its assigned criteria among the active ones, and
 * the global judge_model takes any active criterion no member covers; without a
 * panel, judge_model judges everything.
 *
 * Active criteria: the globally enabled criteria for the active profile (what
 * eval_runner uses), or the profile's enabled criteria_config for any other profile.
 */
export function effectiveJudges(
  config: JudgeConfig,
  profileId: string | null = config.active_profile_id,
): string[] {
  const active =
    profileId === config.active_profile_id
      ? config.criteria.filter((c) => c.enabled).map((c) => c.id)
      : Object.entries(config.profiles.find((p) => p.id === profileId)?.criteria_config ?? {})
          .filter(([, cc]) => cc.enabled)
          .map(([id]) => id)

  const panel = config.panels.find((p) => p.profile_id === profileId)
  if (!panel || panel.judges.length === 0) return [config.judge_model]

  const judges = new Set<string>()
  const covered = new Set<string>()
  for (const member of panel.judges) {
    const mine = member.assigned_criteria.filter((id) => active.includes(id))
    if (mine.length === 0) continue
    judges.add(member.model)
    mine.forEach((id) => covered.add(id))
  }
  if (active.some((id) => !covered.has(id))) judges.add(config.judge_model)
  return [...judges]
}

/** True when `model` would evaluate its own outputs under the given profile. */
export function judgesItself(
  config: JudgeConfig,
  model: string,
  profileId: string | null = config.active_profile_id,
): boolean {
  return effectiveJudges(config, profileId).includes(model)
}
