import requests as req
import sys

BASE = "http://127.0.0.1:8001"

data = {
    "business_name": "Lumina Skin Studio",
    "industry": "Beauty & Aesthetics",
    "business_description": (
        "A boutique facial and skin treatment studio offering personalised skincare consultations, "
        "signature facials, chemical peels, microneedling, and LED therapy. "
        "We focus on science-backed, results-driven treatments using dermatologist-approved products."
    ),
    "target_customers": (
        "Women and men aged 25-55 who want visible skin improvements without visiting a medical clinic. "
        "Busy professionals who value expertise, personalised care, and convenient online booking."
    ),
    "main_problem": (
        "Clients can't find estheticians they trust. Booking is scattered across DMs and calls. "
        "Follow-up care advice is inconsistent and clients forget what products were recommended."
    ),
    "desired_outcome": (
        "A branded platform where clients book treatments online, receive post-care instructions, "
        "track their skin journey with photos, and the studio owner manages all appointments and "
        "client notes from a single dashboard — with automated reminders and AI-powered skin tips."
    ),
    "needs_ai": "AI skin assessment questionnaire, personalised post-treatment care plans, automated rebooking reminders",
    "budget_range": "Medium (10k-30k)",
    "timeline": "3-4 months",
    "email": "demo@luminaskin.com",
    "whatsapp": "+1234567890",
}

print("Submitting Lumina Skin Studio to pipeline...")
print("(The server will generate the full preview — this takes a few minutes)")
print()

try:
    r = req.post(f"{BASE}/api/requests", data=data, timeout=600)
    resp = r.json()
    req_id = resp.get("id")
    print(f"Created request #{req_id}")
    print()
    print(f">>> Open: http://localhost:5175/result/{req_id}")
except req.exceptions.Timeout:
    print("Request timed out but pipeline may still be running on the server.")
    print("Check: http://localhost:5175/result/1")
except Exception as e:
    print(f"Error: {e}")
