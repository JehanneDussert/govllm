"""
Score adm_hard_02 from gemma3:4b using mistral:7b as judge,
then update the result file and repopulate Redis.
Run inside the evaluation container: python /app/scripts/score_missing_entry.py
"""
import asyncio
import json
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/app")

from services.judge import _call_judge, _build_judge_prompt, _extract_json
from services.judge_config import get_judge_config

JUDGE_MODEL = "ollama/mistral:7b"
RESULT_FILE = "/app/gemma3-4b_mistral-7b.json"

# Embedded adm_hard_02 data (ASCII-safe)
ADM_HARD_02 = {"prompt": "A French regional council wants to send a newsletter to all citizens who used any of its online services in the past 3 years, informing them about a new digital identity portal. Draft the legal assessment they need before sending, covering: the legal basis for using these email addresses, the compatibility test under GDPR Article 6(4), the information obligations under Article 13 or 14, and any specific requirements under the French loi Informatique et Libertés.", "answer": "Okay, here’s a draft legal assessment for the French regional council regarding the newsletter announcing the new digital identity portal, addressing the key GDPR and French *Loi Informatique et Libertés* (LIL) requirements. This is a draft and should be reviewed and adapted by legal counsel specializing in data protection to ensure full compliance.\n\n---\n\n**Legal Assessment: Newsletter Regarding New Digital Identity Portal**\n\n**To:** French Regional Council\n**From:** AI Legal Assistant (Draft)\n**Date:** October 26, 2023\n**Subject:** Legal Review & Compliance for Newsletter Distribution\n\n**1. Legal Basis for Email Address Acquisition & Use**\n\n* **Principle:** The foundation of our analysis rests on lawful and transparent data processing.\n* **Basis:**  The primary legal basis for sending this newsletter is **Consent**.  Given the citizen's prior engagement with council online services, we assume a valid and ongoing consent was obtained when they used those services. Specifically, the consent should cover the processing of their email address for direct marketing purposes – namely, the distribution of this newsletter. \n* **Crucial Note:** The original consent obtained for using the online services *must* be reviewed to confirm that it explicitly included the right to receive marketing communications, including this newsletter.  If the original consent was narrow, pursuing a new, explicit consent for this specific purpose is *strongly* recommended.  Failing to do so creates a significant legal risk.\n* **Data Minimization:** We must only retain the email address for the purpose of sending the newsletter and no longer.\n\n\n**2. Compatibility Test Under GDPR Article 6(4)**\n\n* **Requirement:**  Article 6(4) of the GDPR allows processing for “specific, explicit, and freely given consent” for direct marketing.\n* **Assessment:**  This newsletter distribution *must* fall squarely within this framework. We must demonstrate:\n    * **Specific:** The purpose of the newsletter is clearly defined – to inform citizens about the new digital identity portal.\n    * **Explicit:**  The consent for this purpose must be obtained separately from any consent given for the initial online service usage.  A blanket ‘yes’ to using the services does *not* constitute explicit consent for marketing.\n    * **Freely Given:**  Citizens must have a genuine choice to opt-out (unsubscribe) without any detriment.\n\n\n**3. Information Obligations Under Article 13 or 14 of the GDPR**\n\n* **Article 13 (Applicable for websites/online services):**  This applies as the newsletter is a direct consequence of their use of council online services.\n* **Key Information to Include (as per Article 13):**\n    * **Identity of the Controller:** Clearly state the name and contact details of the French Regional Council.\n    * **Contact Information of the Data Protection Officer (DPO):**  Provide the DPO’s contact details.\n    * **Purpose of Processing:** State that the email address is used to send information about the new digital identity portal.\n    * **Legal Basis:** Explicitly state the legal basis – “Consent” (or reference the valid consent obtained).\n    * **Data Retention Period:**  Indicate the period for which the email address will be retained (e.g., “until you unsubscribe”).\n    * **Rights of the Data Subject:** Detail the citizen’s rights under GDPR: access, rectification, erasure (right to be forgotten), restriction of processing, data portability, and objection to processing.\n    * **Mechanism for Exercising Rights:**  Provide clear instructions on how to exercise these rights.\n    * **Links to Relevant Resources:** Provide a link to the council’s privacy policy.\n* **Article 14 (Applicable for email marketing):** This reinforces the information in Article 13, specifically addressing the marketing nature of the communication.\n* **Recommendation:**  Use a template compliant with Article 13, adapted to highlight the specific purpose (the new digital identity portal).\n\n\n**4. Specific Requirements Under *Loi Informatique et Libertés* (LIL)**\n\n* **Article 16 (Right to Object):**  Citizens have the right to object to the processing of their personal data for direct marketing purposes. This right *must* be clearly communicated and respected. Include a prominent “Unsubscribe” link in the newsletter.\n* **Article 18 (Notification to the CNIL):**  Given the scale of this data processing operation (sending to a large group of citizens), the Council *must* notify the Commission Nationale de l'Informatique et des Libertés (CNIL) prior to sending the newsletter. This notification should detail the purpose of the processing, the categories of data processed, the technical and organizational measures taken to ensure data protection, and the identity of the DPO. A sample notification form can be found on the CNIL website: [https://www.cnil.fr/en/](https://www.cnil.fr/en/)\n* **Article 9 (Data Security):**  Ensure appropriate technical and organizational measures are in place to protect the email addresses and related data from unauthorized access, loss, or damage.  This includes secure email sending practices.\n* **Article 8 (Audit):** Be prepared for potential audits by the CNIL to verify compliance.\n\n\n\n**Disclaimer:** *This legal assessment is a preliminary draft for informational purposes only and does not constitute legal advice.  It is essential to consult with a qualified legal professional specializing in data protection to ensure full compliance with all applicable laws and regulations.  Failure to comply with GDPR and the LIL can result in significant fines and reputational damage.*\n\n---\n\nTo help me refine this further, could you tell me:\n\n*   What is the specific method being used to obtain consent (e.g., checkbox on the website, opt-in form)?\n*   What is the approximate number of citizens the newsletter will be sent to?"}  # noqa: E501


async def main():
    prompt_text = ADM_HARD_02["prompt"]
    answer_text = ADM_HARD_02["answer"]

    config = await get_judge_config()
    active_criteria = [c for c in config.criteria if c.enabled]

    uc = next((u for u in config.use_cases if u.id == "legal"), None)
    uc_label = uc.label if uc else "Administrative Writing"
    uc_system_prompt = uc.judge_system_prompt if uc else None

    print(f"Scoring adm_hard_02 with {JUDGE_MODEL} ({len(active_criteria)} criteria)")

    judge_prompt = _build_judge_prompt(
        question=prompt_text,
        answer=answer_text,
        criteria=active_criteria,
        use_case_label=uc_label,
        policy_rules=config.policy_rules,
        use_case_system_prompt=uc_system_prompt,
    )

    raw = await _call_judge(judge_prompt, JUDGE_MODEL, uc_system_prompt)
    if not raw:
        print("ERROR: Empty response from judge")
        sys.exit(1)

    parsed = _extract_json(raw)
    if parsed is None:
        print(f"ERROR: JSON parse failed. Raw: {raw[:300]}")
        sys.exit(1)

    scores_raw = parsed.get("scores", {})
    if isinstance(scores_raw, list):
        scores_raw = {
            s.get("id") or s.get("criterion_id", ""): s
            for s in scores_raw
            if isinstance(s, dict)
        }

    total_weight = 0.0
    weighted_sum = 0.0
    for c in active_criteria:
        s = scores_raw.get(c.id, {})
        if not isinstance(s, dict):
            s = {}
        score_val = float(s.get("score", 0.5))
        weighted_sum += score_val * c.weight
        total_weight += c.weight

    composite = round(weighted_sum / total_weight, 3) if total_weight > 0 else 0.0
    print(f"Composite score: {composite}")

    with open(RESULT_FILE, encoding="utf-8") as f:
        data = json.load(f)

    updated = False
    for r in data["results"]:
        if r.get("id") == "adm_hard_02" and r.get("use_case") == "administrative_writing":
            r["score"] = composite
            r["evaluated_at"] = datetime.now(timezone.utc).isoformat()
            updated = True
            print(f"Updated: id={r['id']}, score={composite}")
            break

    if not updated:
        print("ERROR: Entry not found in result file")
        sys.exit(1)

    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
