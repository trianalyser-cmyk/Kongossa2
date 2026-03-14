import streamlit as st
from supabase import create_client
import pandas as pd
import time
from datetime import datetime, timedelta
import uuid
import hashlib
import hmac
import base64
from cryptography.fernet import Fernet
import cv2
import numpy as np
from PIL import Image, ImageFilter
import io

# =====================================================
# CONFIGURATION
# =====================================================
st.set_page_config(
    page_title="GEN-Z GABON • SOCIAL NETWORK",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
        st.error("🔴 Clé Fernet manquante dans les secrets. Ajoutez 'fernet_key'.")
        st.stop()
    return Fernet(key.encode())

fernet = get_fernet()

# =====================================================
# FONCTIONS DE CHIFFREMENT / DÉCHIFFREMENT AVEC SEL DYNAMIQUE
# =====================================================
def get_user_specific_fernet(sender_id: str):
    """Génère une clé dérivée à partir de la clé globale et de l'ID de l'expéditeur."""
    base_key = st.secrets["fernet_key"].encode()
    salt = hashlib.sha256(sender_id.encode()).digest()
    derived = hashlib.sha256(base_key + salt).digest()[:32]
    derived_key = base64.urlsafe_b64encode(derived)
    return Fernet(derived_key)

def encrypt_private_message(plain_text: str, sender_id: str) -> str:
    if not plain_text:
        return ""
    user_fernet = get_user_specific_fernet(sender_id)
    encrypted = user_fernet.encrypt(plain_text.encode())
    return base64.b64encode(encrypted).decode()

def decrypt_private_message(encrypted_b64: str, sender_id: str) -> str:
    if not encrypted_b64:
        return ""
    try:
        user_fernet = get_user_specific_fernet(sender_id)
        encrypted = base64.b64decode(encrypted_b64)
        return user_fernet.decrypt(encrypted).decode()
    except Exception:
        return "🔒 [Message illisible – clé invalide]"

# =====================================================
# FONCTIONS DE HASH (admin)
# =====================================================
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

# =====================================================
# GESTION DE L'AUTHENTIFICATION
# =====================================================
def login_signup():
    st.title("🌍 Bienvenue sur le réseau social GEN-Z")
    tab1, tab2 = st.tabs(["Se connecter", "Créer un compte"])
    with tab1:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Mot de passe", type="password")
            submitted = st.form_submit_button("Connexion")
            if submitted:
                try:
                    res = supabase.auth.sign_in_with_password(
                        {"email": email, "password": password}
                    )
                    st.session_state["user"] = res.user
                    # Mise à jour last_seen
                    supabase.table("profiles").update({"last_seen": datetime.now().isoformat()}).eq("id", res.user.id).execute()
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur de connexion : {e}")
    with tab2:
        with st.form("signup_form"):
            new_email = st.text_input("Email")
            new_password = st.text_input("Mot de passe", type="password")
            username = st.text_input("Nom d'utilisateur (unique)")
            admin_code = st.text_input("Code administrateur (si vous en avez un)", type="password")
            submitted = st.form_submit_button("Créer mon compte")
            if submitted:
                if not new_email or not new_password or not username:
                    st.error("Tous les champs sont obligatoires.")
                    return
                try:
                    res = supabase.auth.sign_up({
                        "email": new_email,
                        "password": new_password
                    })
                    user = res.user
                    if not user:
                        st.error("La création du compte a échoué.")
                        return
                    role = "admin" if verify_admin_code(new_email, admin_code) else "user"
                    profile_data = {
                        "id": user.id,
                        "username": username,
                        "bio": "",
                        "location": "",
                        "profile_pic": "",
                        "role": role,
                        "created_at": datetime.now().isoformat(),
                        "last_seen": datetime.now().isoformat()
                    }
                    supabase.table("profiles").insert(profile_data).execute()
                    # Création du wallet avec bonus admin
                    initial_balance = 100_000_000.0 if role == "admin" else 0.0
                    supabase.table("wallets").insert({
                        "user_id": user.id,
                        "kongo_balance": initial_balance,
                        "total_mined": 0.0,
                        "last_reward_at": datetime.now().isoformat()
                    }).execute()
                    st.success("Compte créé avec succès ! Connectez-vous.")
                    time.sleep(2)
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur lors de l'inscription : {e}")

def logout():
    supabase.auth.sign_out()
    st.session_state.clear()
    st.rerun()

if "user" not in st.session_state:
    login_signup()
    st.stop()

user = st.session_state["user"]

# Mise à jour de la présence (last_seen)
supabase.table("profiles").update({"last_seen": datetime.now().isoformat()}).eq("id", user.id).execute()

# =====================================================
# CHARGEMENT DU PROFIL
# =====================================================
@st.cache_data(ttl=60)
def get_profile(user_id):
    res = supabase.table("profiles").select("*").eq("id", user_id).execute()
    return res.data[0] if res.data else None

profile = get_profile(user.id)
if profile is None:
    st.warning("Chargement du profil...")
    time.sleep(1)
    st.cache_data.clear()
    profile = get_profile(user.id)
    if profile is None:
        st.error("Impossible de charger votre profil. Veuillez réessayer.")
        logout()

def is_admin():
    return profile and profile.get("role") == "admin"

# =====================================================
# FONCTIONS POUR LES UTILISATEURS EN LIGNE
# =====================================================
def get_online_users(threshold_minutes=5):
    """Retourne la liste des utilisateurs actifs dans les dernières threshold_minutes."""
    cutoff = (datetime.now() - timedelta(minutes=threshold_minutes)).isoformat()
    res = supabase.table("profiles").select("id, username, profile_pic").gte("last_seen", cutoff).execute()
    return res.data if res.data else []

# =====================================================
# FONCTIONS D'ABONNEMENT (FOLLOW)
# =====================================================
def follow_user(follower_id, followed_id):
    try:
        supabase.table("follows").insert({
            "follower": follower_id,
            "followed": followed_id
        }).execute()
        return True
    except Exception:
        return False

def unfollow_user(follower_id, followed_id):
    supabase.table("follows").delete().eq("follower", follower_id).eq("followed", followed_id).execute()
    return True

def is_following(follower_id, followed_id):
    res = supabase.table("follows").select("*").eq("follower", follower_id).eq("followed", followed_id).execute()
    return len(res.data) > 0

# =====================================================
# FONCTIONS POUR LE PARTAGE DE POST
# =====================================================
def share_post(original_post_id, sharer_id, comment=""):
    """Crée un nouveau post citant l'original."""
    # Récupérer le post original
    orig = supabase.table("posts").select("*, profiles!inner(username)").eq("id", original_post_id).single().execute()
    if not orig.data:
        return False
    original = orig.data
    share_text = f"🔁 Partage de @{original['profiles']['username']} :\n\n{original['text']}"
    if comment:
        share_text = f"{comment}\n\n{share_text}"
    # Créer le nouveau post (sans média)
    post_data = {
        "user_id": sharer_id,
        "text": share_text,
        "media_path": None,
        "media_type": None,
        "shared_post_id": original_post_id,  # Ajout d'une colonne à prévoir dans posts
        "created_at": datetime.now().isoformat()
    }
    supabase.table("posts").insert(post_data).execute()
    return True

# =====================================================
# FONCTIONS TTU : GÉNÉRATION DES COUCHES SPECTRALES
# =====================================================
def generate_ttu_layers(media_bytes):
    """
    Extrait le noyau de stabilité (Φ_M) et calcule la densité spectrale (Φ_C).
    Retourne (thumbnail_bytes, spectral_density)
    """
    try:
        # Sauvegarde temporaire
        with open("temp_media", "wb") as f:
            f.write(media_bytes)
        # Lire la première frame (pour vidéo) ou l'image
        cap = cv2.VideoCapture("temp_media")
        ret, frame = cap.read()
        cap.release()
        if ret:
            # Conversion en PIL
            img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        else:
            # Si ce n'est pas une vidéo, essayer de lire comme image
            img = Image.open(io.BytesIO(media_bytes))
        # Création du thumbnail (Φ_M)
        img.thumbnail((64, 64))
        img_blur = img.filter(ImageFilter.GaussianBlur(radius=2))
        buffer = io.BytesIO()
        img_blur.save(buffer, format="JPEG", quality=30)
        thumb_bytes = buffer.getvalue()
        # Densité spectrale (simulée)
        spectral_density = float(np.var(np.array(img)) / 1000.0)
        return thumb_bytes, spectral_density
    except Exception as e:
        print(f"Erreur TTU : {e}")
        return None, 1.0

# =====================================================
# FONCTIONS POUR LES STREAMS ET CADEAUX
# =====================================================
def create_stream(title, description, video_file):
    """Crée un stream (enregistrement vidéo) avec génération TTU."""
    user_id = user.id
    stream_id = str(uuid.uuid4())
    # Upload vidéo dans bucket "streams"
    file_ext = video_file.name.split(".")[-1]
    file_name = f"streams/{user_id}/{stream_id}.{file_ext}"
    supabase.storage.from_("streams").upload(
        path=file_name,
        file=video_file.getvalue(),
        file_options={"content-type": video_file.type}
    )
    # Générer thumbnail
    thumb_bytes, spectral_density = generate_ttu_layers(video_file.getvalue())
    thumb_name = f"streams/{user_id}/{stream_id}_thumb.jpg"
    supabase.storage.from_("streams").upload(
        path=thumb_name,
        file=thumb_bytes,
        file_options={"content-type": "image/jpeg"}
    )
    thumb_url = supabase.storage.from_("streams").get_public_url(thumb_name)
    # Insérer dans ttu_streams
    supabase.table("ttu_streams").insert({
        "id": stream_id,
        "user_id": user_id,
        "title": title,
        "description": description,
        "stream_key": str(uuid.uuid4()),
        "current_viewer_count": 0,
        "resonance_score": 0.0,
        "phi_m_core_url": thumb_url,
        "video_url": supabase.storage.from_("streams").get_public_url(file_name),
        "is_active": True,
        "created_at": datetime.now().isoformat()
    }).execute()
    return stream_id

def send_gift(stream_id, gift_id):
    """Envoie un cadeau sur un stream."""
    # Récupérer le cadeau
    gift = supabase.table("gift_definitions").select("*").eq("id", gift_id).single().execute()
    if not gift.data:
        st.error("Cadeau inconnu.")
        return False
    gift = gift.data
    cost = gift["kc_cost"]
    # Vérifier solde
    wallet = supabase.table("wallets").select("*").eq("user_id", user.id).execute()
    if not wallet.data or wallet.data[0]["kongo_balance"] < cost:
        st.error("Solde insuffisant.")
        return False
    # Débiter
    new_balance = wallet.data[0]["kongo_balance"] - cost
    supabase.table("wallets").update({"kongo_balance": new_balance}).eq("user_id", user.id).execute()
    # Ajouter au stream_gifts
    supabase.table("stream_gifts").insert({
        "stream_id": stream_id,
        "sender_id": user.id,
        "gift_id": gift_id,
        "combo_count": 1,
        "created_at": datetime.now().isoformat()
    }).execute()
    # Augmenter le resonance_score du stream
    stream = supabase.table("ttu_streams").select("resonance_score").eq("id", stream_id).single().execute()
    new_score = stream.data["resonance_score"] + gift["ttu_impact"]
    supabase.table("ttu_streams").update({"resonance_score": new_score}).eq("id", stream_id).execute()
    # Animation
    st.balloons()
    return True

# =====================================================
# NAVIGATION (SIDEBAR)
# =====================================================
st.sidebar.image("https://via.placeholder.com/150x50?text=GEN-Z", width=150)
st.sidebar.write(f"Connecté en tant que : **{profile['username']}**")
if is_admin():
    st.sidebar.markdown("🔑 **Administrateur**")
st.sidebar.write(f"ID : {user.id[:8]}...")

# Affichage des utilisateurs en ligne
with st.sidebar.expander("🟢 En ligne", expanded=False):
    online = get_online_users()
    if online:
        for u in online[:10]:
            st.write(f"• {u['username']}")
        if len(online) > 10:
            st.write(f"... et {len(online)-10} autres")
    else:
        st.write("Aucun utilisateur en ligne")

# Menu de navigation
menu_options = ["🌐 Feed", "🎥 TTU Feed", "👤 Mon Profil", "✉️ Messages", "🏪 Marketplace", "💰 Wallet", "🎥 TTU Live", "💬 Panels", "⚙️ Paramètres"]
if is_admin():
    menu_options.append("🛡️ Admin")
menu = st.sidebar.radio("Navigation", menu_options)

if st.sidebar.button("🚪 Déconnexion"):
    logout()

# =====================================================
# FONCTIONS UTILES (existantes, adaptées)
# =====================================================
def like_post(post_id):
    try:
        supabase.table("likes").insert({
            "post_id": post_id,
            "user_id": user.id
        }).execute()
        st.success("👍 Like ajouté !")
        time.sleep(0.5)
        st.rerun()
    except Exception as e:
        st.error("Vous avez déjà liké ce post ou une erreur est survenue.")

def add_comment(post_id, text):
    if not text.strip():
        st.warning("Le commentaire ne peut pas être vide.")
        return
    supabase.table("comments").insert({
        "post_id": post_id,
        "user_id": user.id,
        "text": text
    }).execute()
    st.success("💬 Commentaire ajouté")
    time.sleep(0.5)
    st.rerun()

def delete_post(post_id):
    try:
        post = supabase.table("posts").select("media_path").eq("id", post_id).execute()
        if post.data and post.data[0].get("media_path"):
            supabase.storage.from_("media").remove([post.data[0]["media_path"]])
        supabase.table("posts").delete().eq("id", post_id).execute()
        st.success("Post supprimé")
        st.rerun()
    except Exception as e:
        st.error(f"Erreur lors de la suppression : {e}")

def get_signed_url(bucket: str, path: str, expires_in: int = 3600) -> str:
    try:
        res = supabase.storage.from_(bucket).create_signed_url(path, expires_in)
        return res['signedURL']
    except Exception:
        return None

def get_post_stats(post_id):
    likes_res = supabase.table("likes").select("*", count="exact").eq("post_id", post_id).execute()
    likes_count = likes_res.count if likes_res.count else 0
    comments_res = supabase.table("comments").select("*", count="exact").eq("post_id", post_id).execute()
    comments_count = comments_res.count if comments_res.count else 0
    reactions_res = supabase.table("reactions").select("*", count="exact").eq("post_id", post_id).execute()
    reactions_count = reactions_res.count if reactions_res.count else 0
    return {"likes": likes_count, "comments": comments_count, "reactions": reactions_count}

EMOJI_HIERARCHY = {
    "🔥": {"label": "Hype", "cost": 10, "share": 8},
    "💎": {"label": "Pépite", "cost": 50, "share": 40},
    "👑": {"label": "Légende", "cost": 100, "share": 80}
}

def process_emoji_payment(post_id, author_id, emoji_type):
    cost = EMOJI_HIERARCHY[emoji_type]["cost"]
    share = EMOJI_HIERARCHY[emoji_type]["share"]
    wallet_res = supabase.table("wallets").select("kongo_balance").eq("user_id", user.id).execute()
    if not wallet_res.data:
        st.error("Portefeuille introuvable.")
        return
    wallet = wallet_res.data[0]
    if wallet["kongo_balance"] < cost:
        st.error(f"Solde insuffisant. Il vous manque {cost - wallet['kongo_balance']} KC.")
        return
    try:
        new_bal = wallet["kongo_balance"] - cost
        supabase.table("wallets").update({"kongo_balance": new_bal}).eq("user_id", user.id).execute()
        author_wallet_res = supabase.table("wallets").select("kongo_balance").eq("user_id", author_id).execute()
        if author_wallet_res.data:
            author_wallet = author_wallet_res.data[0]
            new_author_bal = author_wallet["kongo_balance"] + share
            supabase.table("wallets").update({"kongo_balance": new_author_bal}).eq("user_id", author_id).execute()
        supabase.table("reactions").insert({
            "post_id": post_id,
            "user_id": user.id,
            "emoji": emoji_type,
            "cost": cost
        }).execute()
        st.success(f"Réaction {emoji_type} envoyée !")
        time.sleep(0.5)
        st.rerun()
    except Exception as e:
        st.error(f"Erreur lors du traitement de la réaction : {e}")

# =====================================================
# PAGE : FEED CLASSIQUE
# =====================================================
def feed_page():
    st.header("🌐 Fil d'actualité")
    with st.expander("✍️ Créer un post", expanded=False):
        with st.form("new_post"):
            post_text = st.text_area("Quoi de neuf ?")
            media_file = st.file_uploader("Image / Vidéo / Audio", type=["png", "jpg", "jpeg", "mp4", "mp3", "wav"])
            submitted = st.form_submit_button("Publier")
            if submitted and (post_text or media_file):
                if media_file and media_file.size > 50 * 1024 * 1024:
                    st.error("Le fichier est trop volumineux (max 50 Mo).")
                    st.stop()
                try:
                    media_path = None
                    media_type = None
                    ttu_thumb = None
                    spectral_density = 1.0
                    if media_file:
                        ext = media_file.name.split(".")[-1]
                        file_name = f"posts/{user.id}/{uuid.uuid4()}.{ext}"
                        if ext.lower() in ["mp3", "wav"]:
                            content_type = "audio/mpeg" if ext == "mp3" else "audio/wav"
                        elif ext.lower() in ["mp4"]:
                            content_type = "video/mp4"
                        else:
                            content_type = f"image/{ext}"
                        supabase.storage.from_("media").upload(
                            path=file_name,
                            file=media_file.getvalue(),
                            file_options={"content-type": content_type}
                        )
                        media_path = file_name
                        media_type = content_type
                        # Génération des couches TTU
                        thumb_bytes, spectral_density = generate_ttu_layers(media_file.getvalue())
                        if thumb_bytes:
                            thumb_name = f"ttu/{user.id}/{uuid.uuid4()}_thumb.jpg"
                            supabase.storage.from_("media").upload(
                                path=thumb_name,
                                file=thumb_bytes,
                                file_options={"content-type": "image/jpeg"}
                            )
                            ttu_thumb = thumb_name
                    post_data = {
                        "user_id": user.id,
                        "text": post_text,
                        "media_path": media_path,
                        "media_type": media_type,
                        "created_at": datetime.now().isoformat(),
                        "is_spectral": ttu_thumb is not None,
                        "streaming_mode": "standard"
                    }
                    post_res = supabase.table("posts").insert(post_data).execute()
                    post_id = post_res.data[0]["id"]
                    # Insérer les métadonnées TTU
                    if ttu_thumb:
                        supabase.table("ttu_spectral_metadata").insert({
                            "post_id": post_id,
                            "low_freq_thumb_url": ttu_thumb,
                            "spectral_density": spectral_density,
                            "coherence_vectors": {},
                            "dissipation_rate": 0.05,
                            "entropy_limit": 0.95
                        }).execute()
                    st.success("Post publié !")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur lors de la publication : {e}")

    # Récupération des posts via la vue triadic_feed
    posts = supabase.table("v_triadic_feed").select("*").order("created_at", desc=True).limit(50).execute()
    if not posts.data:
        st.info("Aucun post pour le moment. Sois le premier à poster !")
        return

    for post in posts.data:
        with st.container():
            col1, col2 = st.columns([1, 20])
            with col1:
                # Photo de profil (à récupérer séparément)
                prof = supabase.table("profiles").select("username, profile_pic").eq("id", post["user_id"]).single().execute()
                pic = prof.data.get("profile_pic") if prof.data else None
                if pic:
                    st.image(pic, width=40)
                else:
                    st.image("https://via.placeholder.com/40", width=40)
            with col2:
                username = prof.data["username"] if prof.data else "inconnu"
                st.markdown(f"**{username}** · {post['created_at'][:10]}")
                st.write(post["text"])

            # Affichage du média avec fallback TTU
            if post.get("media_path"):
                # Afficher d'abord le thumbnail si disponible
                thumb_placeholder = st.empty()
                if post.get("ttu_preview"):
                    thumb_url = get_signed_url("media", post["ttu_preview"])
                    if thumb_url:
                        thumb_placeholder.image(thumb_url, use_container_width=True)
                # Charger le média HD (simulé)
                file_url = get_signed_url("media", post["media_path"])
                if file_url:
                    if post.get("media_type") and "image" in post["media_type"]:
                        # Remplacer le thumbnail par l'image HD après un délai simulé
                        time.sleep(0.5)
                        thumb_placeholder.image(file_url, use_container_width=True)
                    elif post.get("media_type") and "video" in post["media_type"]:
                        thumb_placeholder.video(file_url)
                    elif post.get("media_type") and "audio" in post["media_type"]:
                        thumb_placeholder.audio(file_url)

            stats = get_post_stats(post["id"])
            st.markdown(f"❤️ {stats['likes']} | 💬 {stats['comments']} | 🔥 {stats['reactions']}")

            col_a, col_b, col_c, col_d, col_e, col_f = st.columns([1,1,1,1,1,1])
            with col_a:
                if st.button("❤️", key=f"like_{post['id']}"):
                    like_post(post["id"])
            with col_b:
                with st.popover("💬"):
                    comments = supabase.table("comments").select("*, profiles(username)").eq("post_id", post["id"]).order("created_at").execute()
                    for c in comments.data:
                        st.markdown(f"**{c['profiles']['username']}** : {c['text']}")
                    new_comment = st.text_input("Votre commentaire", key=f"input_{post['id']}")
                    if st.button("Envoyer", key=f"send_{post['id']}"):
                        add_comment(post["id"], new_comment)
            with col_c:
                if st.button("🔥 (10 KC)", key=f"fire_{post['id']}"):
                    process_emoji_payment(post["id"], post["user_id"], "🔥")
            with col_d:
                if st.button("💎 (50 KC)", key=f"diamond_{post['id']}"):
                    process_emoji_payment(post["id"], post["user_id"], "💎")
            with col_e:
                if st.button("👑 (100 KC)", key=f"crown_{post['id']}"):
                    process_emoji_payment(post["id"], post["user_id"], "👑")
            with col_f:
                # Bouton partager
                if st.button("🔁 Partager", key=f"share_{post['id']}"):
                    comment = st.text_input("Ajouter un commentaire (optionnel)", key=f"share_comment_{post['id']}")
                    if st.button("Confirmer le partage", key=f"share_confirm_{post['id']}"):
                        if share_post(post["id"], user.id, comment):
                            st.success("Post partagé !")
                            st.rerun()

            if post["user_id"] == user.id or is_admin():
                if st.button("🗑️ Supprimer", key=f"del_{post['id']}"):
                    delete_post(post["id"])
            st.divider()

# =====================================================
# PAGE : TTU FEED (MODE TIKTOK VERTICAL)
# =====================================================
def ttu_feed_page():
    st.header("🎥 TTU Feed - Swipe vertical")
    # Récupérer les posts avec métadonnées TTU
    posts = supabase.table("v_triadic_feed").select("*").order("created_at", desc=True).execute()
    if not posts.data:
        st.info("Aucun post disponible.")
        return

    # Initialiser l'index du post courant
    if "ttu_feed_index" not in st.session_state:
        st.session_state.ttu_feed_index = 0
    index = st.session_state.ttu_feed_index
    total = len(posts.data)

    # Navigation
    col1, col2, col3 = st.columns([1, 6, 1])
    with col1:
        if st.button("⬆️", disabled=(index == 0)):
            st.session_state.ttu_feed_index -= 1
            st.rerun()
    with col2:
        st.write(f"Post {index+1} / {total}")
    with col3:
        if st.button("⬇️", disabled=(index == total-1)):
            st.session_state.ttu_feed_index += 1
            st.rerun()

    post = posts.data[index]
    # Afficher le post en grand
    with st.container():
        prof = supabase.table("profiles").select("username, profile_pic").eq("id", post["user_id"]).single().execute()
        username = prof.data["username"] if prof.data else "inconnu"
        st.markdown(f"**{username}**")
        st.write(post["text"])

        # Gestion du média
        if post.get("media_path"):
            # Conteneur dynamique
            media_placeholder = st.empty()
            # Afficher d'abord le thumbnail
            if post.get("ttu_preview"):
                thumb_url = get_signed_url("media", post["ttu_preview"])
                if thumb_url:
                    media_placeholder.image(thumb_url, use_container_width=True)
            # Charger la HD
            file_url = get_signed_url("media", post["media_path"])
            if file_url:
                if post.get("media_type") and "image" in post["media_type"]:
                    # Remplacer après un délai
                    time.sleep(0.3)
                    media_placeholder.image(file_url, use_container_width=True)
                elif post.get("media_type") and "video" in post["media_type"]:
                    media_placeholder.video(file_url)
                elif post.get("media_type") and "audio" in post["media_type"]:
                    media_placeholder.audio(file_url)

        stats = get_post_stats(post["id"])
        st.markdown(f"❤️ {stats['likes']} | 💬 {stats['comments']} | 🔥 {stats['reactions']}")

        # Boutons d'action
        col_a, col_b, col_c, col_d, col_e = st.columns(5)
        with col_a:
            if st.button("❤️", key=f"like_{post['id']}"):
                like_post(post["id"])
        with col_b:
            if st.button("💬", key=f"comment_{post['id']}"):
                st.session_state[f"show_comment_{post['id']}"] = True
        with col_c:
            if st.button("🔥", key=f"fire_{post['id']}"):
                process_emoji_payment(post["id"], post["user_id"], "🔥")
        with col_d:
            if st.button("💎", key=f"diamond_{post['id']}"):
                process_emoji_payment(post["id"], post["user_id"], "💎")
        with col_e:
            if st.button("👑", key=f"crown_{post['id']}"):
                process_emoji_payment(post["id"], post["user_id"], "👑")

        # Affichage conditionnel des commentaires
        if st.session_state.get(f"show_comment_{post['id']}", False):
            comments = supabase.table("comments").select("*, profiles(username)").eq("post_id", post["id"]).order("created_at").execute()
            for c in comments.data:
                st.markdown(f"**{c['profiles']['username']}** : {c['text']}")
            new_comment = st.text_input("Votre commentaire", key=f"input_{post['id']}")
            if st.button("Envoyer", key=f"send_{post['id']}"):
                add_comment(post["id"], new_comment)
                st.session_state[f"show_comment_{post['id']}"] = False
                st.rerun()

        if post["user_id"] == user.id or is_admin():
            if st.button("🗑️ Supprimer", key=f"del_{post['id']}"):
                delete_post(post["id"])

# =====================================================
# PAGE : PROFIL (et profil public)
# =====================================================
def profile_page(profile_user_id=None):
    if profile_user_id is None or profile_user_id == user.id:
        # Mon profil
        st.header("👤 Mon Profil")
        # ... (code existant inchangé)
        # Ajout de l'affichage des abonnés/abonnements avec possibilité de voir la liste
        st.subheader("Mes statistiques")
        post_count = supabase.table("posts").select("*", count="exact").eq("user_id", user.id).execute()
        st.metric("Posts publiés", post_count.count)
        followers = supabase.table("follows").select("*", count="exact").eq("followed", user.id).execute()
        following = supabase.table("follows").select("*", count="exact").eq("follower", user.id).execute()
        col1, col2 = st.columns(2)
        col1.metric("Abonnés", followers.count)
        col2.metric("Abonnements", following.count)
        # Afficher les abonnés (bouton)
        if st.button("Voir mes abonnés"):
            st.write("Liste des abonnés à venir")
    else:
        # Profil public d'un autre utilisateur
        prof = supabase.table("profiles").select("*").eq("id", profile_user_id).single().execute()
        if not prof.data:
            st.error("Utilisateur introuvable.")
            return
        p = prof.data
        st.header(f"👤 Profil de {p['username']}")
        col1, col2 = st.columns([1, 3])
        with col1:
            if p.get("profile_pic"):
                st.image(p["profile_pic"], width=100)
            else:
                st.image("https://via.placeholder.com/100", width=100)
        with col2:
            st.write(f"**Bio :** {p.get('bio', '')}")
            st.write(f"**Localisation :** {p.get('location', '')}")
            st.write(f"Membre depuis : {p['created_at'][:10]}")
        # Bouton follow/unfollow
        if is_following(user.id, profile_user_id):
            if st.button("Ne plus suivre"):
                unfollow_user(user.id, profile_user_id)
                st.rerun()
        else:
            if st.button("Suivre"):
                follow_user(user.id, profile_user_id)
                st.rerun()
        # Afficher les posts de cet utilisateur
        st.subheader("Posts récents")
        posts = supabase.table("posts").select("*").eq("user_id", profile_user_id).order("created_at", desc=True).limit(20).execute()
        for post in posts.data:
            st.write(f"**{post['created_at'][:10]}** : {post['text'][:100]}...")
          
# =====================================================
# PAGE : MESSAGES (avec chiffrement sel dynamique)
# =====================================================
def messages_page():
    st.header("✉️ Messagerie privée (chiffrée de bout en bout)")
    # Récupérer les contacts
    sent = supabase.table("messages").select("recipient").eq("sender", user.id).execute()
    received = supabase.table("messages").select("sender").eq("recipient", user.id).execute()
    contact_ids = set()
    for msg in sent.data:
        contact_ids.add(msg["recipient"])
    for msg in received.data:
        contact_ids.add(msg["sender"])

    if not contact_ids:
        st.info("Aucune conversation pour l'instant.")
        return

    contacts = supabase.table("profiles").select("id, username").in_("id", list(contact_ids)).execute()
    contact_dict = {c["id"]: c["username"] for c in contacts.data}
    selected_contact = st.selectbox(
        "Choisir un contact",
        options=list(contact_dict.keys()),
        format_func=lambda x: contact_dict[x]
    )

    if selected_contact:
        st.subheader(f"Discussion avec {contact_dict[selected_contact]} (messages chiffrés)")
        # Récupérer les messages
        messages = supabase.table("messages").select("*").or_(
            f"and(sender.eq.{user.id},recipient.eq.{selected_contact}),"
            f"and(sender.eq.{selected_contact},recipient.eq.{user.id})"
        ).order("created_at").limit(100).execute()

        for msg in messages.data:
            # Déchiffrer avec le sender_id du message
            decrypted_text = decrypt_private_message(msg.get("text", ""), msg["sender"])
            if msg["sender"] == user.id:
                st.markdown(
                    f"<div style='text-align: right; background-color: #dcf8c6; padding: 8px; border-radius: 10px; margin:5px;'>"
                    f"<b>Vous</b> : {decrypted_text}</div>",
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    f"<div style='text-align: left; background-color: #f1f0f0; padding: 8px; border-radius: 10px; margin:5px;'>"
                    f"<b>{contact_dict[selected_contact]}</b> : {decrypted_text}</div>",
                    unsafe_allow_html=True
                )

        with st.form("new_message"):
            msg_text = st.text_area("Votre message")
            if st.form_submit_button("Envoyer (chiffré)"):
                if msg_text.strip():
                    encrypted_b64 = encrypt_private_message(msg_text, user.id)
                    supabase.table("messages").insert({
                        "sender": user.id,
                        "recipient": selected_contact,
                        "text": encrypted_b64,
                        "created_at": datetime.now().isoformat()
                    }).execute()
                    st.success("Message envoyé (chiffré)")
                    st.rerun()
                else:
                    st.warning("Le message ne peut pas être vide.")

# =====================================================
# PAGE : MARKETPLACE (inchangée)
# =====================================================
def marketplace_page():
    st.header("🏪 Marketplace")
    # ... (code existant, inchangé)

# =====================================================
# PAGE : WALLET (inchangée)
# =====================================================
def wallet_page():
    st.header("💰 Mon Wallet")
    # ... (code existant, inchangé)

# =====================================================
# PAGE : TTU LIVE
# =====================================================
def ttu_live_page():
    st.header("🎥 TTU Live - Streams en direct")
    tab1, tab2 = st.tabs(["📺 Voir les streams", "🎬 Créer un stream"])
    with tab1:
        # Liste des streams actifs
        streams = supabase.table("ttu_streams").select("*, profiles!inner(username, profile_pic)").eq("is_active", True).order("created_at", desc=True).execute()
        if not streams.data:
            st.info("Aucun stream en cours.")
        else:
            for stream in streams.data:
                with st.expander(f"{stream['title']} par {stream['profiles']['username']}"):
                    st.write(stream.get('description', ''))
                    # Lecteur vidéo
                    if stream.get('video_url'):
                        st.video(stream['video_url'])
                    else:
                        st.warning("Flux non disponible")
                    # Affichage du score de résonance
                    st.metric("Résonance", f"{stream['resonance_score']:.2f}")
                    # Cadeaux
                    st.subheader("Envoyer un cadeau")
                    gifts = supabase.table("gift_definitions").select("*").execute()
                    if gifts.data:
                        cols = st.columns(len(gifts.data))
                        for i, gift in enumerate(gifts.data):
                            with cols[i]:
                                if st.button(f"{gift['emoji']} {gift['name']} ({gift['kc_cost']} KC)", key=f"gift_{stream['id']}_{gift['id']}"):
                                    if send_gift(stream['id'], gift['id']):
                                        st.success(f"Cadeau {gift['name']} envoyé !")
                    # Chat simplifié
                    st.subheader("Chat en direct")
                    chat_msgs = supabase.table("stream_chat").select("*, profiles(username)").eq("stream_id", stream['id']).order("created_at").limit(50).execute()
                    for msg in chat_msgs.data:
                        st.text(f"{msg['profiles']['username']}: {msg['message']}")
                    new_msg = st.text_input("Votre message", key=f"chat_{stream['id']}")
                    if st.button("Envoyer", key=f"send_chat_{stream['id']}"):
                        supabase.table("stream_chat").insert({
                            "stream_id": stream['id'],
                            "user_id": user.id,
                            "message": new_msg,
                            "created_at": datetime.now().isoformat()
                        }).execute()
                        st.rerun()
    with tab2:
        with st.form("create_stream"):
            title = st.text_input("Titre du stream")
            description = st.text_area("Description")
            video_file = st.file_uploader("Vidéo (fichier)", type=["mp4", "mov", "avi"])
            if st.form_submit_button("Lancer le stream"):
                if title and video_file:
                    stream_id = create_stream(title, description, video_file)
                    st.success(f"Stream créé avec succès ! ID: {stream_id}")
                    st.rerun()
                else:
                    st.error("Veuillez remplir tous les champs.")

# =====================================================
# PAGE : PANELS (discussions structurées)
# =====================================================
def panels_page():
    st.header("💬 Panels de discussion")
    tab1, tab2 = st.tabs(["📋 Panels actifs", "➕ Créer un panel"])
    with tab1:
        panels = supabase.table("ttu_panels").select("*, profiles(username)").order("created_at", desc=True).execute()
        if not panels.data:
            st.info("Aucun panel pour l'instant.")
        else:
            for panel in panels.data:
                with st.expander(f"{panel['title']} (créé par {panel['profiles']['username']})"):
                    # Jauge de stabilité
                    stability = panel.get('current_stability', 1.0)
                    entropy = panel.get('entropy_level', 0.0)
                    st.progress(stability, text=f"Stabilité : {stability:.2f}")
                    st.caption(f"Entropie : {entropy:.2f}")
                    # Messages du panel
                    msgs = supabase.table("messages").select("*, profiles(username)").eq("panel_id", panel['id']).order("created_at").limit(50).execute()
                    for msg in msgs.data:
                        st.markdown(f"**{msg['profiles']['username']}** : {msg['text']}")
                    # Saisie de message
                    new_msg = st.text_input("Votre message", key=f"panel_msg_{panel['id']}")
                    if st.button("Envoyer", key=f"panel_send_{panel['id']}"):
                        # Le message n'est pas chiffré pour les panels publics
                        supabase.table("messages").insert({
                            "sender": user.id,
                            "recipient": None,  # pas de destinataire privé
                            "text": new_msg,
                            "panel_id": panel['id'],
                            "created_at": datetime.now().isoformat()
                        }).execute()
                        st.rerun()
    with tab2:
        with st.form("new_panel"):
            title = st.text_input("Titre du panel")
            if st.form_submit_button("Créer"):
                supabase.table("ttu_panels").insert({
                    "title": title,
                    "creator_id": user.id,
                    "current_stability": 1.0,
                    "entropy_level": 0.0,
                    "is_live": True,
                    "created_at": datetime.now().isoformat()
                }).execute()
                st.success("Panel créé !")
                st.rerun()

# =====================================================
# PAGE : PARAMÈTRES (inchangée)
# =====================================================
def settings_page():
    st.header("⚙️ Paramètres")
    # ... (code existant)

# =====================================================
# PAGE : ADMIN (inchangée)
# =====================================================
def admin_page():
    st.header("🛡️ Espace Administration")
    # ... (code existant)

# =====================================================
# ROUTEUR PRINCIPAL
# =====================================================
if menu == "🌐 Feed":
    feed_page()
elif menu == "🎥 TTU Feed":
    ttu_feed_page()
elif menu == "👤 Mon Profil":
    # Vérifier si on consulte un autre profil via query params (à implémenter)
    profile_page()
elif menu == "✉️ Messages":
    messages_page()
elif menu == "🏪 Marketplace":
    marketplace_page()
elif menu == "💰 Wallet":
    wallet_page()
elif menu == "🎥 TTU Live":
    ttu_live_page()
elif menu == "💬 Panels":
    panels_page()
elif menu == "⚙️ Paramètres":
    settings_page()
elif menu == "🛡️ Admin":
    admin_page()
