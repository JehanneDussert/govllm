# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

"""
Identity & Access forensic orchestration — takes a CandidateWindow (output of
services/identity_ingestion.py) and evaluates it against the
identity_access_governance profile's checklist criteria, reusing the same
judge-calling machinery as the ground truth checklist mode.

Skeleton: end-to-end tested only once a real log source feeds
services/identity_ingestion.py — the judge-calling path itself is the same
one already validated by the ground truth corpus.
"""

from __future__ import annotations

from services.groundtruth import _call_judge_checklist, compute_checklist_score
from services.judge_config import get_judge_config
from shared.schemas.identity_access import CandidateWindow

NOTIFICATION_SCORE_THRESHOLD = 0.5  # any criterion scoring below this triggers notification

IDENTITY_CHECKLIST_QUESTIONS: dict[str, dict[str, str]] = {
    "scope_conformity": {
        "q1": (
            "Le compte a-t-il accédé à des ressources ou périmètres fonctionnels "
            "qui ne relèvent pas de son rôle ou service déclaré ? "
            "[oui=violation / non=conforme]"
        ),
        "q2": (
            "Un accès hors périmètre habituel a-t-il fait l'objet d'une élévation "
            "de privilège tracée et justifiée (ticket, workflow d'approbation) ? "
            "[oui=conforme / non=violation]"
        ),
        "q3": (
            "Le périmètre auquel le compte a accédé correspond-il aux droits qui "
            "lui ont été formellement attribués (matrice d'habilitation), "
            "indépendamment du comportement observé sur cette fenêtre ? "
            "[oui=conforme / non=violation]"
        ),
        "q4": (
            "Une tentative d'accès hors périmètre a-t-elle été bloquée ou "
            "signalée par le contrôle d'accès plutôt que silencieusement "
            "autorisée ? [oui=conforme / non=violation]"
        ),
    },
    "volume_conformity": {
        "q1": (
            "Le volume de données consultées ou exportées sur la période "
            "dépasse-t-il significativement la baseline habituelle du compte ? "
            "[oui=violation / non=conforme]"
        ),
        "q2": (
            "Un volume inhabituel constaté est-il corrélé à une activité métier "
            "documentée (campagne, migration, extraction planifiée) ? "
            "[oui=conforme / non=violation]"
        ),
        "q3": (
            "Le rythme des requêtes ou téléchargements est-il compatible avec "
            "une activité humaine normale, sans signe d'automatisation ou de "
            "script ? [oui=conforme / non=violation]"
        ),
        "q4": (
            "Une alerte de volumétrie anormale a-t-elle déclenché une action de "
            "contrôle (notification, limitation, revue) ? "
            "[oui=conforme / non=violation]"
        ),
    },
    "temporal_conformity": {
        "q1": (
            "Les connexions ou actions du compte ont-elles eu lieu à des "
            "horaires incompatibles avec le profil d'activité habituel (nuit, "
            "week-end, jour férié) sans justification ? "
            "[oui=violation / non=conforme]"
        ),
        "q2": (
            "Une activité en horaire atypique est-elle cohérente avec un motif "
            "documenté (astreinte, fuseau horaire déclaré, intervention "
            "planifiée) ? [oui=conforme / non=violation]"
        ),
        "q3": (
            "La durée ou la fréquence des sessions sur la fenêtre observée "
            "est-elle cohérente avec la structure habituelle des journées de "
            "travail du compte (pas de session anormalement longue ou "
            "fragmentée) ? [oui=conforme / non=violation]"
        ),
        "q4": (
            "En cas d'activité hors plage horaire habituelle, le compte a-t-il "
            "été soumis à une vérification complémentaire (MFA, validation "
            "manager) ? [oui=conforme / non=violation]"
        ),
    },
    "session_geo_consistency": {
        "q1": (
            "Le compte présente-t-il des connexions successives dont l'écart "
            "temps/distance est incompatible avec un déplacement physique "
            "plausible ? [oui=violation / non=conforme]"
        ),
        "q2": (
            "En cas d'usage de VPN/proxy détecté, cet usage est-il cohérent "
            "avec une politique d'accès distant documentée pour ce compte ? "
            "[oui=conforme / non=violation]"
        ),
        "q3": (
            "La session présente-t-elle une rupture d'identifiant technique "
            "(user-agent, device fingerprint) incohérente avec l'historique du "
            "compte ? [oui=violation / non=conforme]"
        ),
        "q4": (
            "Face à une incohérence de session détectée, existe-t-il une trace "
            "de ré-authentification ou de vérification complémentaire (MFA) ? "
            "[oui=conforme / non=violation]"
        ),
    },
    "sensitive_export_justification": {
        "q1": (
            "L'export du compte porte-t-il sur des données sensibles (Art. 9 "
            "RGPD — santé, origine raciale/ethnique, opinions politiques/"
            "religieuses, données biométriques ou génétiques) sans base légale "
            "ni finalité documentée pour cet export ? "
            "[oui=violation / non=conforme]"
        ),
        "q2": (
            "L'export a-t-il fait l'objet d'une validation ou approbation "
            "préalable tracée (workflow, ticket, hiérarchie) ? "
            "[oui=conforme / non=violation]"
        ),
        "q3": (
            "Le volume et le périmètre de l'export sont-ils strictement limités "
            "à la finalité déclarée, sans extraction excédentaire ? "
            "[oui=conforme / non=violation]"
        ),
        "q4": (
            "Un export de données sensibles a-t-il généré une trace d'audit "
            "dédiée (traçabilité renforcée Art. 30/32) ? "
            "[oui=conforme / non=violation]"
        ),
    },
}


def _describe_window(window: CandidateWindow) -> str:
    lines = [
        f"Account: {window.account_id}",
        f"Window: {window.window_start.isoformat()} to {window.window_end.isoformat()}",
        f"Baseline (last {window.baseline.window_days} days, {window.baseline.sample_count} events): "
        f"known scopes={sorted(window.baseline.known_scopes)}, "
        f"known source IPs={sorted(window.baseline.known_source_ips)}, "
        f"typical total volume per {window.baseline.volume_window_hours:g}h window="
        f"{window.baseline.volume_mean:.1f} (stddev={window.baseline.volume_stddev:.1f}, "
        f"over {window.baseline.volume_window_count} active windows), "
        f"active hours={sorted(window.baseline.active_hours)}",
        f"Deviation flags: scope={window.flags.scope_deviation}, "
        f"volume={window.flags.volume_deviation}, "
        f"temporal={window.flags.temporal_deviation}, "
        f"session_geo={window.flags.session_geo_deviation}",
        "Events in this window:",
    ]
    for e in window.events:
        lines.append(
            f"  - {e.timestamp.isoformat()} | account={e.account_id} | "
            f"action={e.action} | scope={e.resource_scope} | volume={e.volume} | "
            f"source_ip={e.source_ip} | session={e.session_id}"
        )
    return "\n".join(lines)


def _build_identity_prompt(criterion: str, window: CandidateWindow) -> str:
    questions = IDENTITY_CHECKLIST_QUESTIONS[criterion]
    q_block = "\n".join(f"{qid}: {text}" for qid, text in questions.items())
    reasoning_template = "\n".join(
        f"{qid}: [your analysis] → true (compliant) | false (violation)"
        for qid in questions
    )
    return (
        "Do not default to compliant — critically assess each question against "
        "the account's baseline and the observed events independently.\n\n"
        "You are a forensic auditor evaluating an account's access log window "
        "against a regulatory compliance checklist.\n\n"
        f"{_describe_window(window)}\n\n"
        f"CHECKLIST — Criterion: {criterion}\n"
        "true = compliant (no violation detected). false = violation detected.\n\n"
        f"{q_block}\n\n"
        "STEP 1 — Reason through each question. Write one line per question:\n"
        f"{reasoning_template}\n\n"
        "STEP 2 — Based on your step 1 conclusions above, output JSON only: "
        '{"answers": {' + ", ".join(f'"{q}": <true|false>' for q in questions) + '}, '
        '"reason": "<one-sentence summary>"}'
    )


async def evaluate_candidate_window(window: CandidateWindow) -> dict:
    """
    Evaluate a candidate window against every identity_access_governance
    criterion enabled in the active profile. Returns per-criterion verdicts
    plus an overall notification_threshold_reached flag.
    """
    config = await get_judge_config()
    profile = next(
        (p for p in config.profiles if p.id == "identity_access_governance"), None
    )
    enabled_criteria = (
        [cid for cid, cc in profile.criteria_config.items() if cc.enabled]
        if profile
        else list(IDENTITY_CHECKLIST_QUESTIONS.keys())
    )

    verdicts = []
    for criterion in enabled_criteria:
        if criterion not in IDENTITY_CHECKLIST_QUESTIONS:
            continue
        prompt = _build_identity_prompt(criterion, window)
        answers, reason, latency_ms = await _call_judge_checklist(
            prompt, config.judge_model
        )
        score = compute_checklist_score(answers) if answers else 0.0
        verdicts.append(
            {
                "criterion_id": criterion,
                "answers": answers or {},
                "score": score,
                "flagged": score < NOTIFICATION_SCORE_THRESHOLD,
                "reason": reason,
                "latency_ms": latency_ms,
            }
        )

    return {
        "account_id": window.account_id,
        "window_start": window.window_start,
        "window_end": window.window_end,
        "deviation_score": window.deviation_score,
        "verdicts": verdicts,
        "notification_threshold_reached": any(v["flagged"] for v in verdicts),
    }
