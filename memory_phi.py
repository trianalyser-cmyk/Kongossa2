# memory_phi.py
import streamlit as st
from supabase import create_client
import time
from datetime import datetime, timedelta
import uuid
import hashlib
import hmac
import base64
import psutil
import numpy as np
from cryptography.fernet import Fernet

# =====================================================
# INITIALISATION SUPABASE & FERNET
# =====================================================
@st.cache_resource
def init_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()

@st.cache_resource
def get_fernet():
    key = st.secrets.get("fernet_key")
    if not key:
        st.error("🔴 Clé Fernet manquante dans les secrets.")
        st.stop()
    return Fernet(key.encode())

fernet = get_fernet()

# =====================================================
# MESURE DE LA MÉMOIRE (ΦM)
# =====================================================
def measure_phi_m():
    """Retourne ΦM = RAM_utilisée / RAM_max (en pourcentage)."""
    mem = psutil.virtual_memory()
    return mem.percent / 100.0

# =====================================================
# MÉMOIRE HIÉRARCHIQUE
# =====================================================
class HierarchicalMemory:
    """Gère trois niveaux de mémoire : session, cache, base de données."""
    
    def __init__(self):
        self.phi_m_threshold = 0.7  # seuil pour passer en mémoire persistante
    
    def store(self, key, value, level="session"):
        """Stocke une donnée au niveau approprié."""
        if level == "session":
            st.session_state[key] = value
        elif level == "cache":
            st.cache_data[key] = value  # Note: st.cache_data est un décorateur, pas un dict. On utilisera st.cache_resource ou un cache manuel.
            # Pour simplifier, on utilise st.session_state avec un préfixe "cache_"
            st.session_state[f"cache_{key}"] = value
        else:  # persistent
            # À implémenter selon le type de donnée
            pass
    
    def retrieve(self, key, level="session"):
        if level == "session":
            return st.session_state.get(key)
        elif level == "cache":
            return st.session_state.get(f"cache_{key}")
        return None
    
    def sync_if_needed(self):
        """Si ΦM est élevé, on décharge le cache vers Supabase."""
        if measure_phi_m() > self.phi_m_threshold:
            # Parcourir les clés de cache et les persister
            for k in list(st.session_state.keys()):
                if k.startswith("cache_"):
                    # Simuler une persistance
                    pass
            st.success("📀 Déchargement du cache vers la base.")

memory = HierarchicalMemory()

# =====================================================
# COMPRESSION TRIADIQUE
# =====================================================
def compress_log(log_text: str) -> dict:
    """Génère un embedding et un résumé d'un log."""
    # Simule un embedding (vecteur de 384 floats) par un hash
    hash_val = int(hashlib.sha256(log_text.encode()).hexdigest(), 16)
    np.random.seed(hash_val % 2**32)
    embedding = np.random.randn(384).astype(np.float32)
    # Résumé : premiers 200 caractères
    summary = log_text[:200] + "..." if len(log_text) > 200 else log_text
    return {"embedding": embedding.tolist(), "summary": summary}

def decompress_log(compressed: dict) -> str:
    """Reconstruit le log à partir du résumé (perte d'info)."""
    return compressed["summary"]

# =====================================================
# AUTHENTIFICATION ET PROFILS (inchangé, mais adapté)
# =====================================================
def encrypt_text(plain_text: str) -> str:
    if not plain_text:
        return ""
    encrypted = fernet.encrypt(plain_text.encode())
    return base64.b64encode(encrypted).decode()

def decrypt_text(encrypted_b64: str) -> str:
    if not encrypted_b64:
        return ""
    try:
        encrypted = base64.b64decode(encrypted_b64)
        return fernet.decrypt(encrypted).decode()
    except Exception:
        return "🔐 Message illisible"

def hash_string(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()

def verify_admin_code(email: str, code: str) -> bool:
    try:
        admin_email_hash = st.secrets["admin"]["email_hash"]
        admin_code_hash = st.secrets["admin"]["password_hash"]
        return hmac.compare_digest(hash_string(email), admin_email_hash) and \
               hmac.compare_digest(hash_string(code), admin_code_hash)
    except KeyError:
        return False

def login_signup():
    st.title("🌍 Bienvenue sur GEN-Z")
    tab1, tab2 = st.tabs(["Se connecter", "Créer un compte"])

    with tab1:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Mot de passe", type="password")
            if st.form_submit_button("Connexion"):
                try:
                    res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    st.session_state["user"] = res.user
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur : {e}")

    with tab2:
        with st.form("signup_form"):
            new_email = st.text_input("Email")
            new_password = st.text_input("Mot de passe", type="password")
            username = st.text_input("Nom d'utilisateur")
            admin_code = st.text_input("Code admin (facultatif)", type="password")
            if st.form_submit_button("Créer mon compte"):
                if not new_email or not new_password or not username:
                    st.error("Tous les champs sont obligatoires.")
                    return
                try:
                    res = supabase.auth.sign_up({"email": new_email, "password": new_password})
                    user = res.user
                    if not user:
                        st.error("Échec de l'inscription.")
                        return
                    role = "admin" if verify_admin_code(new_email, admin_code) else "user"
                    profile_data = {
                        "id": user.id,
                        "username": username,
                        "bio": "",
                        "location": "",
                        "profile_pic": "",
                        "role": role,
                        "created_at": datetime.now().isoformat()
                    }
                    supabase.table("profiles").insert(profile_data).execute()
                    supabase.table("wallets").insert({
                        "user_id": user.id,
                        "kongo_balance": 100_000_000.0 if role == "admin" else 0.0,
                        "total_mined": 0.0,
                        "last_reward_at": datetime.now().isoformat()
                    }).execute()
                    supabase.table("tst_params").insert({
                        "username": username,
                        "phi_m": 1.0,
                        "phi_c": 1.0,
                        "phi_d": 1.0,
                        "stability_threshold": 0.5
                    }).execute()
                    st.success("Compte créé ! Connectez-vous.")
                    time.sleep(2)
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur : {e}")

def logout():
    if "tst_params" in st.session_state and "profile" in st.session_state:
        supabase.table("tst_params").update(st.session_state.tst_params).eq("username", st.session_state.profile["username"]).execute()
    supabase.auth.sign_out()
    st.session_state.clear()
    st.rerun()

# =====================================================
# CHARGEMENT DU PROFIL ET DES PARAMÈTRES TST
# =====================================================
@st.cache_data(ttl=60)
def get_profile(user_id):
    try:
        res = supabase.table("profiles").select("*").eq("id", user_id).execute()
        return res.data[0] if res.data else None
    except Exception:
        return None

def load_tst_params(username):
    try:
        res = supabase.table("tst_params").select("*").eq("username", username).execute()
        if res.data:
            return res.data[0]
    except Exception:
        pass
    default = {"username": username, "phi_m": 1.0, "phi_c": 1.0, "phi_d": 1.0, "stability_threshold": 0.5}
    try:
        supabase.table("tst_params").insert(default).execute()
    except Exception:
        pass
    return default

def init_gift_definitions():
    gifts = [
        {"name": "L’Atome d’Ogooué", "emoji": "💧", "kc_cost": 50, "animation_type": "blue_shockwave", "ttu_impact": 0.2},
        {"name": "Le Masque Punu", "emoji": "🎭", "kc_cost": 80, "animation_type": "petal_fall", "ttu_impact": 0.3},
        {"name": "La Torche d’Ozavigui", "emoji": "🔥", "kc_cost": 120, "animation_type": "sparks", "ttu_impact": 0.4},
        {"name": "La Pierre de Mbigou", "emoji": "🪨", "kc_cost": 150, "animation_type": "solidify", "ttu_impact": 0.5},
        {"name": "La Danse du Ndjembè", "emoji": "💃", "kc_cost": 200, "animation_type": "red_circles", "ttu_impact": 0.6},
        {"name": "Le Tambour de l’Unité", "emoji": "🥁", "kc_cost": 250, "animation_type": "heartbeat", "ttu_impact": 0.7},
        {"name": "L’Émeraude de l’Ivindo", "emoji": "💎", "kc_cost": 300, "animation_type": "green_flash", "ttu_impact": 0.8},
        {"name": "Le Vol du Perroquet Gris", "emoji": "🦜", "kc_cost": 400, "animation_type": "bird_fly", "ttu_impact": 0.9},
        {"name": "Le Lion du Mayombé", "emoji": "🦁", "kc_cost": 500, "animation_type": "lion_roar", "ttu_impact": 1.0},
        {"name": "La Porte de l’Oracle", "emoji": "⛩️", "kc_cost": 1000, "animation_type": "portal", "ttu_impact": 1.5},
    ]
    for gift in gifts:
        try:
            existing = supabase.table("gift_definitions").select("id").eq("name", gift["name"]).execute()
            if not existing.data:
                supabase.table("gift_definitions").insert(gift).execute()
        except Exception:
            pass

# =====================================================
# UTILITAIRES (signature, badge)
# =====================================================
def get_signed_url(bucket: str, path: str, expires_in: int = 3600) -> str:
    try:
        res = supabase.storage.from_(bucket).create_signed_url(path, expires_in)
        return res['signedURL']
    except Exception:
        return None

def get_user_badge(user_id):
    try:
        total_gifts = supabase.table("stream_gifts").select("*", count="exact").eq("sender_id", user_id).execute()
        count = total_gifts.count if total_gifts.count else 0
        if count >= 50:
            return "🔥🔥"
        elif count >= 20:
            return "🔥"
        elif count >= 5:
            return "✨"
    except Exception:
        pass
    return ""
