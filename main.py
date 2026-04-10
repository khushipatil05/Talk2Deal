import os
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.models.negotiation import NegotiationRequest, NegotiationResponse
from app.services.pricing_engine import PricingEngine
from app.services.llm_service import LLMService
from app.services.gamification import GamificationService
from app.core.database import get_db
from app.data.product_catalog import MOCK_PRODUCT_DATA


# ---------------------------------------------------------
# FastAPI app + template / static setup
# ---------------------------------------------------------

app = FastAPI(title="Talk2Deal – Negotiation API")

# allow browser calls from anywhere (fine for local dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "app", "templates")
STATIC_DIR = os.path.join(BASE_DIR, "app", "static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)

# static folder is optional – create app/static if you want CSS/JS files
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# shared services
llm_service = LLMService()
db = get_db()


# ---------------------------------------------------------
# Auth models
# ---------------------------------------------------------

class UserCredentials(BaseModel):
    user_id: str
    password: str


# ---------------------------------------------------------
# Page routes (HTML)
# ---------------------------------------------------------

@app.get("/", include_in_schema=False)
async def index():
    """
    Redirect root to the login page.
    """
    return RedirectResponse(url="/login")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """
    Client login / registration page.
    """
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/client", response_class=HTMLResponse)
async def client_page(request: Request, user_id: str):
    """
    Negotiation page – requires a valid user_id in query params.
    Example: /client?user_id=user123
    """
    user_doc = db.collection("users").document(user_id).get()
    if not user_doc.exists:
        # if user not found, push them back to login
        return RedirectResponse(url="/login")

    return templates.TemplateResponse(
        "client.html",
        {
            "request": request,
            "user_id": user_id,
            "products": MOCK_PRODUCT_DATA,
        },
    )


# ---------------------------------------------------------
# Auth APIs
# ---------------------------------------------------------

@app.post("/api/register")
async def register_user(creds: UserCredentials):
    """
    Create a new user in Firestore: collection 'users', doc id = user_id.
    NOTE: password is stored in plain text – OK for a college project,
    not OK for real production.
    """
    users_ref = db.collection("users")
    doc_ref = users_ref.document(creds.user_id)

    if doc_ref.get().exists:
        raise HTTPException(status_code=400, detail="User already exists")

    doc_ref.set({"password": creds.password})
    return {"status": "ok", "message": "User registered"}


@app.post("/api/login")
async def login_user(creds: UserCredentials):
    """
    Validate existing user.
    """
    doc = db.collection("users").document(creds.user_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="User not found")

    data = doc.to_dict()
    if data.get("password") != creds.password:
        raise HTTPException(status_code=401, detail="Incorrect password")

    return {"status": "ok", "message": "Login successful"}


# ---------------------------------------------------------
# Utility API – product list for the client page
# ---------------------------------------------------------

@app.get("/api/products")
async def list_products() -> Dict[str, Any]:
    """
    Small helper so the client can fetch available products.
    """
    return MOCK_PRODUCT_DATA


# ---------------------------------------------------------
# Main negotiation endpoint
# ---------------------------------------------------------

@app.post("/negotiate", response_model=NegotiationResponse)
def handle_negotiation(request: NegotiationRequest):
    """
    Single negotiation turn.
    """

    if request.product_id not in MOCK_PRODUCT_DATA:
        raise HTTPException(status_code=404, detail="Product not found.")

    try:
        pricing_engine = PricingEngine(
            product_id=request.product_id,
            user_id=request.user_id,
        )
        gamification_service = GamificationService(user_id=request.user_id)

        # 1. Analyze user message
        llm_output = llm_service.analyze_user_input(request.user_message)

        # 2. Pricing engine decides what to do
        pricing_decision = pricing_engine.generate_counteroffer(llm_output)

        # 3. Generate AI text
        ai_text = llm_service.generate_ai_response(
            user_message=request.user_message,
            pricing_decision=pricing_decision,
        )

        # 4. Persist state & history
        pricing_engine.update_state_after_turn(
            llm_output=llm_output,
            pricing_decision=pricing_decision,
            user_message=request.user_message,
        )

        # 5. Gamification
        points_awarded = gamification_service.award_points(pricing_decision)
        if points_awarded > 0:
            current_points = gamification_service.get_current_points()
            ai_text += (
                f"\n\n✨ Bonus! You earned {points_awarded} Bargain Points. "
                f"Total: {current_points}."
            )

        # 6. Final price calculation
        base_price = MOCK_PRODUCT_DATA[request.product_id]["base_price"]
        final_price = base_price
        is_over = pricing_decision.decision_type == "ACCEPT"
        new_offer_value = None
        offer_unit = None

        if pricing_decision.decision_type == "COUNTER":
            discount_pct = (pricing_decision.offer_value or 0.0) / 100
            final_price = base_price * (1 - discount_pct)
            new_offer_value = pricing_decision.offer_value
            offer_unit = pricing_decision.offer_unit

        elif pricing_decision.decision_type == "ACCEPT":
            state = pricing_engine.data_access.get_negotiation_state(
                pricing_engine.state_key
            )
            last_offer_pct = state.get("last_offer_pct", 0.0)
            final_price = base_price * (1 - last_offer_pct / 100)

        elif pricing_decision.decision_type == "PERK":
            new_offer_value = pricing_decision.offer_value
            offer_unit = pricing_decision.offer_unit

        return NegotiationResponse(
            ai_response_text=ai_text,
            current_price=round(final_price, 2),
            is_negotiation_over=is_over,
            new_offer=new_offer_value,
            offer_unit=offer_unit,
        )

    except HTTPException:
        # let FastAPI handle these as-is
        raise
    except Exception as exc:
        # this ensures the client ALWAYS gets JSON, not raw text
        print(f"Unexpected error in /negotiate: {exc}")
        raise HTTPException(
            status_code=500, detail="Internal server error during negotiation."
        )
