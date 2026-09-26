from app.services.risk_engine import calculate_risk_score


                       
identity_results = {

    "name": {
        "reference": "AARAV SHARMA",
        "extracted": "AARAV SHARMA",
        "status": "MATCH"
    },

    "dob": {
        "reference": "12/04/2001",
        "extracted": "12/04/2001",
        "status": "MATCH"
    },

    "document_number": {
        "reference": "DEMO123456",
        "extracted": "DEMO123456",
        "status": "MATCH"
    },

    "address": {
        "reference": "Sample City",
        "extracted": "Sample City",
        "status": "MATCH"
    }
}


            
ocr_confidence = 90.71


                
quality_result = {
    "overall": "POOR"
}


                  
indicator_result = {
    "highest_severity": "LOW"
}


                
result = calculate_risk_score(
    identity_results,
    ocr_confidence,
    quality_result,
    indicator_result
)


print("\n========== RISK ASSESSMENT ==========\n")

print("Risk Score:")
print(result["score"])

print("\nRisk Band:")
print(result["risk_band"])

print("\nReasons:")

for reason in result["reasons"]:
    print("-", reason)

print("\nRecommendation:")
print(result["recommendation"])

print("\n=====================================")
