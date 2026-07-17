"""Delete FuelForm Coach request and create a fresh coaching demo."""
import json
import sys

from app.infrastructure.db.session import SessionLocal
from app.domain.models.request import Request
from app.domain.models.preview_chat_message import PreviewChatMessage
from app.application.pipelines.orchestrator import generate_full_pipeline
from app.infrastructure.web.reference_scraper import fetch_reference_metadata


def main():
    db = SessionLocal()
    for rid in (3,):
        req = db.query(Request).filter(Request.id == rid).first()
        if req:
            db.query(PreviewChatMessage).filter(PreviewChatMessage.request_id == rid).delete()
            db.delete(req)
            db.commit()
            print(f"Deleted request #{rid} ({req.concept_name})")

    new = Request(
        business_name="Fuel & Form Coaching",
        industry="Health, Fitness & Nutrition",
        business_description=(
            "I'm a licensed dietitian and certified fitness coach. I create personalized meal plans "
            "and workout programs for busy professionals who want to lose fat, build muscle, or improve "
            "energy without extreme diets. Clients get weekly check-ins, habit tracking, and plan "
            "adjustments based on progress photos and body metrics."
        ),
        target_customers=(
            "Men and women aged 28-45, office workers and entrepreneurs. They struggle with consistency, "
            "eating out often, and not knowing what to eat or how to train."
        ),
        main_problem=(
            "Everything runs through WhatsApp and Google Sheets. I manually send PDF meal plans, "
            "voice-note workout instructions, and chase clients for weekly weigh-ins. I cannot scale past 25 clients."
        ),
        desired_outcome=(
            "A branded client portal where clients log meals, see workout plans, track weight and habits, "
            "book check-in calls, and get reminders. Premium online coaching brand."
        ),
        reference_url="https://www.trainerize.com",
        what_you_like=(
            "Clean client dashboard, progress photos, habit tracking, workout logging, and meal plan delivery "
            "in one place. Professional feel — clients see their plan daily instead of digging through WhatsApp."
        ),
        needs_ai="yes",
        budget_range="Standard scope",
        timeline="1-2 months",
        email="test.fuelform.demo@example.com",
        whatsapp="+96170123456",
        status="new",
    )
    db.add(new)
    db.commit()
    db.refresh(new)
    request_id = new.id
    print(f"Created request #{request_id}")

    metadata = fetch_reference_metadata(new.reference_url)
    new.reference_metadata = json.dumps(metadata)
    db.commit()
    db.close()

    db2 = SessionLocal()
    try:
        result = generate_full_pipeline(db2, request_id)
        req = db2.query(Request).filter(Request.id == request_id).first()
        print(f"Pipeline done: concept={req.concept_name}, score={req.business_fit_score}")
        if req.visual_demo_json:
            demo = json.loads(req.visual_demo_json)
            print("feature_cards:", [c.get("title") for c in demo.get("feature_cards", [])])
            pc = demo.get("preview_content", {})
            print("image_theme:", pc.get("image_theme"))
            svcs = (pc.get("website") or {}).get("services") or []
            if svcs:
                print("preview services:", [s.get("name") for s in svcs])
        print(f"VIEW: http://localhost:5175/result/{request_id}")
        return request_id
    finally:
        db2.close()


if __name__ == "__main__":
    main()
