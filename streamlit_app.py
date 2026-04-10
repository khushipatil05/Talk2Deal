# streamlit_app.py
import streamlit as st
import requests
import json
import random

# --- Configuration ---
# NOTE: Ensure your FastAPI server is running on http://127.0.0.1:8000
FASTAPI_URL = "http://127.0.0.1:8000/negotiate" 
PRODUCT_ID = "P001"
USER_ID = "U" + str(random.randint(100, 999)) # Simulate a unique user

# --- Mock Product Data for Display (Must match FastAPI's P001) ---
PRODUCT_DATA = {
    "name": "Luxury Silk Scarf",
    "base_price": 200.0,
    "image_url": "https://images.unsplash.com/photo-1542496658-e39a6dd3d4e7" # Placeholder image
}

# --- Streamlit Session State Initialization ---
def init_session_state():
    """Initializes the chat history and product state."""
    if 'history' not in st.session_state:
        st.session_state.history = [
            {"role": "assistant", "content": "Welcome! I'm Talk2Deal, your negotiation assistant. How much of a discount are you looking for on this item?"}
        ]
    if 'current_price' not in st.session_state:
        st.session_state.current_price = PRODUCT_DATA["base_price"]
    if 'negotiation_over' not in st.session_state:
        st.session_state.negotiation_over = False

# --- Core API Call Function ---
def call_negotiation_api(user_message):
    """Sends user message to the FastAPI backend and handles the response."""
    data = {
        "user_id": USER_ID,
        "product_id": PRODUCT_ID,
        "user_message": user_message
    }
    
    try:
        response = requests.post(FASTAPI_URL, json=data)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        return response.json()
        
    except requests.exceptions.RequestException as e:
        st.error(f"Error connecting to FastAPI: {e}")
        st.session_state.history.append({"role": "assistant", "content": "I'm having trouble connecting to my pricing engine right now. Please try again later."})
        return None

# --- Main Streamlit UI ---
init_session_state()

st.set_page_config(page_title="Talk2Deal Negotiation Assistant", layout="centered")
st.title("🤝 Talk2Deal: AI Negotiation")
st.subheader(f"Negotiating for: **{PRODUCT_DATA['name']}**")

# --- Product and Price Display ---
col1, col2 = st.columns([1, 2])

with col1:
    st.image(PRODUCT_DATA["image_url"], width=150)

with col2:
    st.metric(
        label="Current Negotiated Price",
        value=f"${st.session_state.current_price:.2f}"
    )
    st.caption(f"Base Price: ${PRODUCT_DATA['base_price']:.2f}")
    
st.markdown("---")

# --- Chat Display ---
for message in st.session_state.history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- Chat Input ---
if not st.session_state.negotiation_over:
    if user_prompt := st.chat_input("Ask for a discount, or accept the current offer..."):
        
        # 1. Add user message to history
        st.session_state.history.append({"role": "user", "content": user_prompt})
        
        # 2. Display user message immediately
        with st.chat_message("user"):
            st.markdown(user_prompt)
            
        # 3. Call the FastAPI Backend
        with st.spinner("AI is thinking..."):
            api_response = call_negotiation_api(user_prompt)
        
        # 4. Process API Response
        if api_response:
            # Update state with the new price and status
            st.session_state.current_price = api_response["current_price"]
            st.session_state.negotiation_over = api_response["is_negotiation_over"]
            
            # Display AI response
            ai_text = api_response["ai_response_text"]
            
            # Add reward/perk information if provided
            if api_response["new_offer"] and api_response["offer_unit"] == "POINTS":
                 ai_text += f" (Note: We've added **{int(api_response['new_offer'])} loyalty points** to your account!)"

            with st.chat_message("assistant"):
                st.markdown(ai_text)
            
            # 5. Add AI response to history
            st.session_state.history.append({"role": "assistant", "content": ai_text})

else:
    st.success("🎉 Negotiation Successful! Price locked. Proceed to checkout.")
    st.balloons()