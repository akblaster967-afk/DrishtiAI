from app.services.identity_checker import compare_identity


reference_fields = {
    "name": "AARAV SHARMA",
    "dob": "12/04/2001",
    "document_number": "DEMO123456",
    "address": "Sample City"
}


extracted_fields = {
    "name": "AARAV SHARMA",
    "dob": "12/04/2001",
    "document_number": "DEMO123456",
    "address": "Sample City"
}


results = compare_identity(
    reference_fields,
    extracted_fields
)


print("\n========== IDENTITY CHECK ==========\n")

for field, result in results.items():

    print(field.upper())

    print("Reference :", result["reference"])
    print("Extracted :", result["extracted"])
    print("Status    :", result["status"])

    print("------------------------------------")

print("\n====================================")
