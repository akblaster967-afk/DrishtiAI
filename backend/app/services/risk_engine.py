from __future__ import annotations



def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)



def _status(result):
    return str((result or {}).get("status", "")).upper()



def _band_from_score(score: int) -> str:
    if score < 25:
        return "Low Risk"
    if score < 50:
        return "Review"
    return "High / Potentially Suspicious"



def _analysis_confidence(
    ocr_confidence,
    quality_result,
    document_verification,
    document_profile=None,
    extraction_conflicts=None,
):
    ocr = _safe_float(ocr_confidence, 0.0)
    quality = str((quality_result or {}).get("overall", "")).upper()
    profile_status = str((document_profile or {}).get("status", "")).upper()
    conflict_count = len(extraction_conflicts or [])

    points = 0
    if ocr >= 85:
        points += 3
    elif ocr >= 70:
        points += 2
    elif ocr >= 55:
        points += 1

    if quality in {"GOOD", "EXCELLENT"}:
        points += 2
    elif quality == "MODERATE":
        points += 1

    if profile_status == "PASS":
        points += 1
    elif profile_status == "REVIEW":
        points -= 1

    if conflict_count == 0:
        points += 1
    elif conflict_count >= 2:
        points -= 1

    if points >= 7:
        return "HIGH"
    if points >= 4:
        return "MEDIUM"
    return "LOW"



def calculate_risk_score(
    identity_results,
    ocr_confidence,
    quality_result,
    indicator_result,
    document_consistency=None,
    reference_comparison=None,
    ai_document_analysis=None,
    document_verification=None,
    cross_document_consistency=None,
    extraction_conflicts=None,
    face_comparison=None,
):
    reasons: list[str] = []
    hard_flags: list[str] = []




    mismatches = []
    uncertainties = []
    for field, result in (identity_results or {}).items():
        if not isinstance(result, dict):
            continue
        status = _status(result)
        if status == "MISMATCH":
            mismatches.append(field)
        elif status in {"PARTIAL", "UNKNOWN"}:
            uncertainties.append(field)

    identity_gate = "FAIL" if mismatches else ("REVIEW" if uncertainties else "PASS")
    if mismatches:
        hard_flags.append("IDENTITY_FIELD_MISMATCH")
        reasons.append("Identity verification failed for: " + ", ".join(mismatches) + ".")
    elif uncertainties:
        reasons.append("Some supplied identity fields could not be fully verified: " + ", ".join(uncertainties) + ".")

    identity_points = 0
    if mismatches:
        reasons.append("Identity verification failed for one or more supplied identity fields; this is a separate identity gate.")
    elif uncertainties:
        reasons.append("One or more supplied identity fields remain uncertain; this is a separate identity gate.")

    face_comparison = face_comparison or {}
    face_status = str(face_comparison.get("status", "")).upper()
    face_score = _safe_float(face_comparison.get("score"), 0.0)


    face_risk_points = 0
    if face_comparison:
        reasons.append(f"Face matching status: {face_status or 'UNAVAILABLE'}; identity outcome is evaluated separately from document risk.")


    document_consistency = document_consistency or {}
    consistency_band = str(document_consistency.get("band", "")).upper()
    consistency_score = _safe_float(document_consistency.get("score"), 0)
    semantic_points = 0
    if consistency_band == "HIGH":
        semantic_points = min(18, max(8, round(consistency_score * 0.35)))
        reasons.append("Internal consistency checks found strong contradictions.")
    elif consistency_band == "MEDIUM":
        semantic_points = min(9, max(2, round(consistency_score * 0.22)))
        reasons.append("Internal consistency checks found items requiring review.")


    reference_comparison = reference_comparison or {}
    reference_points = 0
    ref_band = ""
    ref_score = 0.0
    if reference_comparison.get("available"):
        ref_band = str(reference_comparison.get("band", "")).upper()
        ref_score = _safe_float(reference_comparison.get("score"), 0)
        if ref_band == "HIGH":
            reference_points = min(35, max(22, round(ref_score * 0.45)))
            reasons.append("Reference comparison found substantial content or visual differences.")
            hard_flags.append("REFERENCE_CONTRADICTION")
        elif ref_band == "MEDIUM":
            reference_points = min(14, max(5, round(ref_score * 0.28)))
            reasons.append("Reference comparison found moderate differences that require review.")
        elif ref_score > 0:
            reference_points = min(4, round(ref_score * 0.10))
            reasons.append("Reference comparison found minor differences.")


    ai_document_analysis = ai_document_analysis or {}
    ai_band = str(ai_document_analysis.get("band", "")).upper()
    ai_score = _safe_float(ai_document_analysis.get("score"), 0)
    ai_points = 0
    if ai_band == "HIGH":
        ai_points = min(20, max(12, round(ai_score * 0.28)))
        reasons.append(f"Supporting synthetic-document screening returned HIGH evidence ({ai_score:.1f}/100).")
    elif ai_band == "MEDIUM":
        ai_points = min(8, max(4, round(ai_score * 0.18)))
        reasons.append(f"Supporting synthetic-document screening returned MEDIUM evidence ({ai_score:.1f}/100).")


    document_verification = document_verification or {}
    document_profile = document_verification.get("documentProfile") or {}
    profile_status = str(document_profile.get("status", "")).upper()
    verification_points = 0
    if profile_status == "FAIL":
        verification_points += 10
        reasons.append("Document-family checks do not support the selected document type.")
        hard_flags.append("DOCUMENT_PROFILE_FAIL")
    elif profile_status == "REVIEW":
        verification_points += 3
        reasons.append("Document-family evidence is incomplete and requires review.")

    qr_status = str((document_verification.get("qrCheck") or {}).get("status", "")).upper()
    if qr_status == "MISMATCH":
        verification_points += 25
        hard_flags.append("ENCODED_DATA_MISMATCH")
        reasons.append("Readable QR/encoded data contradicts the extracted document identifier.")
    elif qr_status == "REVIEW":
        verification_points += 2
        reasons.append("Readable QR/encoded data could not be directly tied to the extracted identifier.")

    schema_checks = document_verification.get("schemaChecks") or []
    format_reviews = sum(1 for item in schema_checks if str(item.get("status", "")).upper() == "FORMAT_REVIEW")
    failed_rules = sum(1 for item in schema_checks if str(item.get("status", "")).upper() == "FAIL")
    missing_fields = sum(1 for item in schema_checks if str(item.get("status", "")).upper() == "MISSING")
    verification_points += min(12, failed_rules * 6)
    verification_points += min(4, format_reviews * 2)

    ocr_value = _safe_float(ocr_confidence, 0)
    if ocr_value >= 70 and missing_fields:
        verification_points += min(4, missing_fields * 2)
        reasons.append(f"{missing_fields} expected document field(s) were not reliably established despite good OCR readability.")

    integrity_screening = document_verification.get("integrityScreening") or {}
    integrity_status = str(integrity_screening.get("status") or "").upper()
    integrity_score = _safe_float(integrity_screening.get("score"), 0)
    integrity_points = 0
    if integrity_status == "POSSIBLE_EDITING":
        integrity_points = min(15, max(10, round(integrity_score * 0.22)))
        reasons.append("Document integrity screening found multiple independent signals consistent with possible local editing or regeneration.")
    elif integrity_status == "REVIEW_SIGNAL":
        integrity_points = min(8, max(3, round(integrity_score * 0.12)))
        reasons.append("Document integrity screening found a signal that requires manual review.")

    security_features = document_verification.get("securityFeatures") or {}
    security_status = str(security_features.get("overallStatus") or "").upper()
    security_review_count = int(security_features.get("reviewCount") or 0)
    if security_status == "HIGH":
        verification_points += 4
        reasons.append("Several expected visible security/design cues were not detected.")
    elif security_status == "REVIEW" and security_review_count >= 3:
        verification_points += 2
        reasons.append("Several expected visible security/design cues require manual review.")
    verification_points = min(35, verification_points)

    fabrication_screening = document_verification.get("fabricationScreening") or {}
    fabrication_verdict = str(fabrication_screening.get("verdict") or "").upper()
    fabrication_signals = fabrication_screening.get("signals") or []
    fabrication_high = sum(1 for item in fabrication_signals if str(item.get("severity", "")).upper() == "HIGH")
    fabrication_medium = sum(1 for item in fabrication_signals if str(item.get("severity", "")).upper() == "MEDIUM")
    fabrication_points = min(15, fabrication_high * 6 + fabrication_medium * 3)
    if fabrication_verdict in {"FABRICATED_OR_TAMPERED", "EDITED_OR_SAMPLE_DOCUMENT"}:
        hard_flags.append("FABRICATION_EVIDENCE")
        reasons.append("Fabrication screening found evidence consistent with an edited or sample document.")
    elif fabrication_verdict == "SUSPICIOUS_REQUIRES_REVIEW":
        reasons.append("Fabrication screening found signals that require manual review.")
    verification_points = min(35, verification_points + fabrication_points)


    cross_document_consistency = cross_document_consistency or {}
    cross_status = str(cross_document_consistency.get("status", "")).upper()
    cross_points = 0
    if cross_status == "REVIEW":
        cross_points = min(8, _safe_float(cross_document_consistency.get("score"), 0))
        reasons.extend((cross_document_consistency.get("reasons") or [])[:2])


    indicator_result = indicator_result or {}
    indicators = indicator_result.get("indicators") or []
    highest_severity = str(indicator_result.get("highest_severity", "")).upper()
    indicator_points = 0
    if highest_severity == "HIGH":
        indicator_points = min(10, 8 + min(2, len(indicators)))
        reasons.append("High-severity file-level indicators were detected.")
    elif highest_severity == "MEDIUM":
        indicator_points = min(6, 3 + len(indicators))
        reasons.append("Medium-severity file-level indicators were detected.")
    elif highest_severity == "LOW" and indicators:
        indicator_points = 1
        reasons.append("Low-severity file-level indicators were detected.")

    raw_score = (
        semantic_points + reference_points + ai_points + verification_points
        + cross_points + indicator_points + integrity_points
    )
    score = max(0, min(100, int(round(raw_score))))






    high_modules: list[str] = []
    medium_modules: list[str] = []
    if consistency_band == "HIGH":
        high_modules.append("internal_consistency")
    elif consistency_band == "MEDIUM":
        medium_modules.append("internal_consistency")
    if ref_band == "HIGH":
        high_modules.append("reference_comparison")
    elif ref_band == "MEDIUM":
        medium_modules.append("reference_comparison")
    if ai_band == "HIGH":
        high_modules.append("ai_synthetic_screen")
    elif ai_band == "MEDIUM":
        medium_modules.append("ai_synthetic_screen")
    if qr_status == "MISMATCH" or failed_rules >= 2 or str(document_verification.get("overallStatus") or "").upper() == "HIGH" or fabrication_verdict == "EDITED_OR_SAMPLE_DOCUMENT":
        high_modules.append("document_verification")
    elif profile_status in {"FAIL", "REVIEW"} or qr_status == "REVIEW" or format_reviews:
        medium_modules.append("document_verification")
    if highest_severity == "HIGH":
        high_modules.append("file_indicator")
    elif highest_severity == "MEDIUM":
        medium_modules.append("file_indicator")
    if integrity_status == "POSSIBLE_EDITING":
        high_modules.append("document_integrity")
    elif integrity_status in {"REVIEW_SIGNAL", "INCONCLUSIVE"}:
        medium_modules.append("document_integrity")
    if security_status == "HIGH":
        high_modules.append("security_features")
    elif security_status == "REVIEW":
        medium_modules.append("security_features")

    if high_modules:
        score = max(score, 50)
        reasons.append(
            "At least one configured evidence module is HIGH, so the final risk cannot remain in the LOW band."
        )
    elif medium_modules:
        score = max(score, 25)
        reasons.append(
            "At least one configured evidence module requires REVIEW, so the final risk cannot remain below the review band."
        )

    if qr_status == "MISMATCH":
        score = max(score, 50)

    analysis_confidence = _analysis_confidence(
        ocr_confidence,
        quality_result,
        document_verification,
        document_profile=document_profile,
        extraction_conflicts=extraction_conflicts,
    )

    if ocr_value < 60:
        reasons.append("OCR readability is low; this lowers evidence confidence but is not counted as forgery evidence.")
    if str((quality_result or {}).get("overall", "")).upper() == "POOR":
        reasons.append("Image quality is poor; this lowers analysis confidence but is not itself evidence of forgery.")
    if extraction_conflicts:
        reasons.append(f"{len(extraction_conflicts)} extraction conflict(s) were found between generic OCR and document-specific extraction; verify the affected fields.")


    strong_evidence = bool([f for f in hard_flags if f != "IDENTITY_FIELD_MISMATCH"])
    strong_evidence = strong_evidence or reference_points >= 22 or ai_points >= 12 or failed_rules >= 2 or qr_status == "MISMATCH"

    if analysis_confidence == "LOW" and not strong_evidence:
        score = min(score, 24)
        reasons.append("Evidence confidence is low, so weak screening signals were capped rather than treated as proof of manipulation.")

    risk_band = _band_from_score(score)
    if score < 25:
        screening_outcome = "LOW_RISK"
        recommendation = "No strong manipulation evidence found; normal acceptance workflow may continue after identity gates are considered."
        authenticity_status = "LIKELY_ORIGINAL"
    elif score < 50:
        screening_outcome = "REVIEW"
        recommendation = "Keep the document in screening state and route it for manual review before treating it as verified."
        authenticity_status = "REVIEW_REQUIRED"
    else:
        screening_outcome = "HIGH_RISK"
        recommendation = "Do not accept as verified; escalate for detailed verification."
        authenticity_status = "POSSIBLE_EDITING_OR_INVALIDITY"

    return {
        "score": score,
        "risk_band": risk_band,
        "screening_outcome": screening_outcome,
        "authenticity_status": authenticity_status,
        "reasons": list(dict.fromkeys(reasons)),
        "recommendation": recommendation,
        "identity_gate": {
            "status": identity_gate,
            "mismatches": mismatches,
            "uncertainties": uncertainties,
        },
        "analysis_confidence": analysis_confidence,
        "hard_flags": hard_flags,
        "document_profile": {
            "status": profile_status or "UNAVAILABLE",
            "score": document_profile.get("score"),
            "message": document_profile.get("message"),
        },
        "document_consistency": {
            "score": consistency_score,
            "band": consistency_band or "UNAVAILABLE",
            "pointsAdded": semantic_points,
            "reasons": document_consistency.get("reasons", []),
        },
        "ai_document_screening": {
            "score": ai_score if ai_document_analysis.get("score") is not None else None,
            "band": ai_band or "UNAVAILABLE",
            "signalCount": len(ai_document_analysis.get("signals", []) or []),
            "pointsAdded": ai_points,
        },
        "verification_evidence": {
            "qrStatus": qr_status or "UNAVAILABLE",
            "formatReviewCount": format_reviews,
            "failedRuleCount": failed_rules,
            "missingFieldCount": missing_fields,
            "issuerStatus": str(((document_verification.get("issuerVerification") or {}).get("status", "NOT_CONFIGURED"))),
            "securityStatus": security_status or "UNAVAILABLE",
            "securityReviewCount": security_review_count,
            "fabricationVerdict": fabrication_verdict or "UNAVAILABLE",
            "fabricationSignalCount": len(fabrication_signals),
            "fabricationPointsAdded": fabrication_points,
            "pointsAdded": verification_points,
        },
        "cross_document_consistency": {
            "status": cross_status or "UNAVAILABLE",
            "score": cross_document_consistency.get("score"),
            "comparedDocumentCount": cross_document_consistency.get("comparedDocumentCount", cross_document_consistency.get("checkedDocuments", 0)),
        },
        "score_breakdown": {
            "semanticConsistency": semantic_points,
            "referenceComparison": reference_points,
            "supportingSyntheticScreen": ai_points,
            "verificationEvidence": verification_points,
            "crossDocumentConsistency": cross_points,
            "suspiciousIndicators": indicator_points,
            "identityMatching": identity_points,
            "faceMatching": face_risk_points,
            "identityGate": identity_gate,
            "faceGate": face_status or "NOT_CHECKED",
            "rawWeightedScore": int(round(raw_score)),
            "highEvidenceModules": high_modules,
            "reviewEvidenceModules": medium_modules,
            "minimumRiskBandApplied": "HIGH" if high_modules else "REVIEW" if medium_modules else None,
        },
        "signal_risk_scores": {
            "identity_matching": identity_points,
            "face_matching": face_risk_points,
            "document_consistency": semantic_points,
            "reference_comparison": reference_points,
            "ai_document_screening": ai_points,
            "document_verification": verification_points,
            "cross_document_consistency": cross_points,
            "file_indicators": indicator_points,
            "document_integrity": integrity_points,
        },
    }
