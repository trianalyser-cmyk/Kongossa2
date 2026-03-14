# app.py
import streamlit as st
from memory_phi import login_signup, get_profile, load_tst_params, init_gift_definitions, supabase, user, profile, tst_params, memory
from dissipation_phi import run

st.set_page_config(page_title="GEN-Z GABON", page_icon="🌍", layout="wide")

# Authentification
if "user" not in st.session_state:
    login_signup()
    st.stop()

# Chargement du profil et des paramètres
st.session_state.profile = get_profile(user.id)
if st.session_state.profile is None:
    st.error("Profil introuvable.")
    st.stop()

st.session_state.tst_params = load_tst_params(st.session_state.profile["username"])
init_gift_definitions()  # Une seule fois

# Lancer l'application
run()
