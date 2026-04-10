# streamlit_admin.py

import streamlit as st

from app.core.database import initialize_firebase
from app.services.data_access import DataAccess
from app.data.product_catalog import MOCK_PRODUCT_DATA


st.set_page_config(
    page_title="Talk2Deal Admin Dashboard",
    layout="wide",
)


# -------------------------------------------------------------------
# Firebase / Firestore initialization
# -------------------------------------------------------------------
@st.cache_resource
def get_data_access() -> DataAccess:
    """
    Streamlit-cached DataAccess instance.
    This will call Firebase initialization under the hood.
    """
    # Ensure Firebase is initialized (for clarity; DataAccess also calls get_db)
    initialize_firebase()
    return DataAccess()


def main():
    st.title("🛠 Talk2Deal Admin Dashboard")

    # Try to connect to Firestore
    try:
        data_access = get_data_access()
        st.success("Connected to Firebase Firestore successfully.")
    except Exception as e:
        st.error(f"Failed to connect to Firestore: {e}")
        st.stop()

    # ----------------------------------------------------------------
    # Layout: Tabs for Products and Negotiation State
    # ----------------------------------------------------------------
    tab_products, tab_state = st.tabs(["📦 Product Catalog", "🤝 Negotiation State"])

    # -------------------- PRODUCT CATALOG TAB -----------------------
    with tab_products:
        st.subheader("Product Catalog")

        if not MOCK_PRODUCT_DATA:
            st.info("No products found in MOCK_PRODUCT_DATA.")
        else:
            # Convert dict to simple table
            rows = []
            for product_id, data in MOCK_PRODUCT_DATA.items():
                row = {"product_id": product_id}
                row.update(data)
                rows.append(row)

            st.dataframe(rows, use_container_width=True)

    # -------------------- NEGOTIATION STATE TAB ---------------------
    with tab_state:
        st.subheader("Lookup Negotiation State")

        st.markdown(
            "State key format: `user_id:product_id` "
            "(this is how your `PricingEngine` stores state)."
        )

        state_key = st.text_input("Enter state key")

        if st.button("Fetch state") and state_key:
            try:
                state = data_access.get_negotiation_state(state_key)
                if state:
                    st.json(state)
                else:
                    st.info("No negotiation state found for this key.")
            except Exception as e:
                st.error(f"Error fetching state: {e}")


if __name__ == "__main__":
    main()
# End of file
