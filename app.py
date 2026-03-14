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
# FONCTIONS DE CHIFFREMENT / DÉCHIFFREMENT
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
        return "🔐 Message illisible (erreur de clé)"

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
                        "created_at": datetime.now().isoformat()
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
# NAVIGATION (SIDEBAR)
# =====================================================
st.sidebar.image("https://via.placeholder.com/150x50?text=GEN-Z", width=150)
st.sidebar.write(f"Connecté en tant que : **{profile['username']}**")
if is_admin():
    st.sidebar.markdown("🔑 **Administrateur**")
st.sidebar.write(f"ID : {user.id[:8]}...")

menu_options = ["🌐 Feed", "👤 Mon Profil", "✉️ Messages", "🏪 Marketplace", "💰 Wallet", "⚙️ Paramètres"]
if is_admin():
    menu_options.append("🛡️ Admin")
menu = st.sidebar.radio("Navigation", menu_options)

if st.sidebar.button("🚪 Déconnexion"):
    logout()

# =====================================================
# FONCTIONS UTILES
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
        # Récupérer le chemin du média pour le supprimer du storage
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

# =====================================================
# FONCTIONS POUR LES STATISTIQUES DES POSTS
# =====================================================
def get_post_stats(post_id):
    # Compte réel des likes (gratuits)
    likes_res = supabase.table("likes").select("*", count="exact").eq("post_id", post_id).execute()
    likes_count = likes_res.count if likes_res.count else 0

    # Compte réel des commentaires
    comments_res = supabase.table("comments").select("*", count="exact").eq("post_id", post_id).execute()
    comments_count = comments_res.count if comments_res.count else 0

    # Compte des réactions premium (emojis payants)
    reactions_res = supabase.table("reactions").select("*", count="exact").eq("post_id", post_id).execute()
    reactions_count = reactions_res.count if reactions_res.count else 0

    return {
        "likes": likes_count,
        "comments": comments_count,
        "reactions": reactions_count
    }

# Hiérarchie des emojis payants
EMOJI_HIERARCHY = {
    "🔥": {"label": "Hype", "cost": 10, "share": 8},      # L'auteur gagne 8 KC
    "💎": {"label": "Pépite", "cost": 50, "share": 40},   # L'auteur gagne 40 KC
    "👑": {"label": "Légende", "cost": 100, "share": 80}  # L'auteur gagne 80 KC
}

def process_emoji_payment(post_id, author_id, emoji_type):
    """Gère le paiement d'une réaction émoji premium."""
    cost = EMOJI_HIERARCHY[emoji_type]["cost"]
    share = EMOJI_HIERARCHY[emoji_type]["share"]

    # Vérifier le solde de l'utilisateur
    wallet_res = supabase.table("wallets").select("kongo_balance").eq("user_id", user.id).execute()
    if not wallet_res.data:
        st.error("Portefeuille introuvable.")
        return
    wallet = wallet_res.data[0]
    if wallet["kongo_balance"] < cost:
        st.error(f"Solde insuffisant. Il vous manque {cost - wallet['kongo_balance']} KC.")
        return

    # Vérifier que l'utilisateur n'a pas déjà réagi avec cet émoji sur ce post (optionnel)
    # On peut autoriser plusieurs réactions de types différents

    try:
        # 1. Débiter l'utilisateur
        new_bal = wallet["kongo_balance"] - cost
        supabase.table("wallets").update({"kongo_balance": new_bal}).eq("user_id", user.id).execute()

        # 2. Créditer l'auteur (80% du coût)
        author_wallet_res = supabase.table("wallets").select("kongo_balance").eq("user_id", author_id).execute()
        if author_wallet_res.data:
            author_wallet = author_wallet_res.data[0]
            new_author_bal = author_wallet["kongo_balance"] + share
            supabase.table("wallets").update({"kongo_balance": new_author_bal}).eq("user_id", author_id).execute()

        # 3. Enregistrer la réaction dans la table reactions
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
# PAGES
# =====================================================
def feed_page():
    st.header("🌐 Fil d'actualité")
    with st.expander("✍️ Créer un post", expanded=False):
        with st.form("new_post"):
            post_text = st.text_area("Quoi de neuf ?")
            media_file = st.file_uploader("Image / Vidéo / Audio", type=["png", "jpg", "jpeg", "mp4", "mp3", "wav"])
            submitted = st.form_submit_button("Publier")
            if submitted and (post_text or media_file):
                # Vérification taille fichier
                if media_file and media_file.size > 50 * 1024 * 1024:  # 50 Mo max
                    st.error("Le fichier est trop volumineux (max 50 Mo).")
                    st.stop()
                try:
                    media_path = None
                    media_type = None
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

                    post_data = {
                        "user_id": user.id,
                        "text": post_text,
                        "media_path": media_path,
                        "media_type": media_type,
                        "created_at": datetime.now().isoformat()
                    }
                    supabase.table("posts").insert(post_data).execute()
                    st.success("Post publié !")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur lors de la publication : {e}")

    # Récupération des posts avec les profils
    posts = supabase.table("posts").select(
        "*, profiles!inner(username, profile_pic)"
    ).order("created_at", desc=True).limit(50).execute()

    if not posts.data:
        st.info("Aucun post pour le moment. Sois le premier à poster !")
        return

    for post in posts.data:
        with st.container():
            col1, col2 = st.columns([1, 20])
            with col1:
                pic = post["profiles"].get("profile_pic")
                if pic:
                    st.image(pic, width=40)
                else:
                    st.image("https://via.placeholder.com/40", width=40)
            with col2:
                st.markdown(f"**{post['profiles']['username']}** · {post['created_at'][:10]}")
            st.write(post["text"])

            # Affichage du média
            if post.get("media_path"):
                file_url = get_signed_url("media", post["media_path"])
                if file_url:
                    if post.get("media_type") and "image" in post["media_type"]:
                        st.image(file_url)
                    elif post.get("media_type") and "video" in post["media_type"]:
                        st.video(file_url)
                    elif post.get("media_type") and "audio" in post["media_type"]:
                        st.audio(file_url)
                else:
                    st.warning("Média temporairement indisponible")

            # Statistiques du post
            stats = get_post_stats(post["id"])
            st.markdown(f"❤️ {stats['likes']}  |  💬 {stats['comments']}  |  🔥 {stats['reactions']}")

            # Boutons d'interaction
            col_a, col_b, col_c, col_d, col_e = st.columns([1, 1, 1, 1, 1])
            with col_a:
                if st.button("❤️", key=f"like_{post['id']}"):
                    like_post(post["id"])
            with col_b:
                with st.popover("💬"):
                    comments = supabase.table("comments").select(
                        "*, profiles(username)"
                    ).eq("post_id", post["id"]).order("created_at").execute()
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

            # Bouton de suppression (si propriétaire ou admin)
            if post["user_id"] == user.id or is_admin():
                if st.button("🗑️ Supprimer", key=f"del_{post['id']}"):
                    delete_post(post["id"])

            st.divider()

def profile_page():
    st.header("👤 Mon Profil")
    with st.expander("Changer ma photo de profil", expanded=False):
        uploaded_file = st.file_uploader("Choisir une image", type=["png", "jpg", "jpeg"])
        if uploaded_file:
            # Limite de taille (5 Mo)
            if uploaded_file.size > 5 * 1024 * 1024:
                st.error("Image trop volumineuse (max 5 Mo).")
                st.stop()
            try:
                ext = uploaded_file.name.split(".")[-1]
                file_name = f"avatars/{user.id}/{uuid.uuid4()}.{ext}"
                supabase.storage.from_("avatars").upload(
                    path=file_name,
                    file=uploaded_file.getvalue(),
                    file_options={"content-type": f"image/{ext}"}
                )
                public_url = supabase.storage.from_("avatars").get_public_url(file_name)
                supabase.table("profiles").update({"profile_pic": public_url}).eq("id", user.id).execute()
                st.success("Photo de profil mise à jour")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Erreur lors de l'upload : {e}")

    with st.form("edit_profile"):
        username = st.text_input("Nom d'utilisateur", value=profile["username"])
        bio = st.text_area("Bio", value=profile.get("bio", ""))
        location = st.text_input("Localisation", value=profile.get("location", ""))
        if st.form_submit_button("Mettre à jour"):
            supabase.table("profiles").update({
                "username": username,
                "bio": bio,
                "location": location
            }).eq("id", user.id).execute()
            st.success("Profil mis à jour")
            st.cache_data.clear()
            st.rerun()

    st.subheader("Mes statistiques")
    post_count = supabase.table("posts").select("*", count="exact").eq("user_id", user.id).execute()
    st.metric("Posts publiés", post_count.count)
    followers = supabase.table("follows").select("*", count="exact").eq("followed", user.id).execute()
    following = supabase.table("follows").select("*", count="exact").eq("follower", user.id).execute()
    col1, col2 = st.columns(2)
    col1.metric("Abonnés", followers.count)
    col2.metric("Abonnements", following.count)

def messages_page():
    st.header("✉️ Messagerie privée (chiffrée de bout en bout)")
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
        # Récupérer les messages avec limite pour éviter la surcharge
        messages = supabase.table("messages").select("*").or_(
            f"and(sender.eq.{user.id},recipient.eq.{selected_contact}),"
            f"and(sender.eq.{selected_contact},recipient.eq.{user.id})"
        ).order("created_at").limit(100).execute()

        for msg in messages.data:
            decrypted_text = decrypt_text(msg.get("text", ""))
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
                    encrypted_b64 = encrypt_text(msg_text)
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

def marketplace_page():
    st.header("🏪 Marketplace")
    with st.expander("➕ Ajouter une annonce"):
        with st.form("new_listing"):
            title = st.text_input("Titre")
            description = st.text_area("Description")
            price = st.number_input("Prix (KC)", min_value=0.0, step=0.1)
            media = st.file_uploader("Image du produit", type=["png", "jpg", "jpeg"])
            submitted = st.form_submit_button("Publier l'annonce")
            if submitted and title:
                if media and media.size > 5 * 1024 * 1024:
                    st.error("Image trop volumineuse (max 5 Mo).")
                    st.stop()
                try:
                    media_url = None
                    if media:
                        file_name = f"marketplace/{user.id}/{uuid.uuid4()}.jpg"
                        supabase.storage.from_("marketplace").upload(
                            path=file_name,
                            file=media.getvalue(),
                            file_options={"content-type": media.type}
                        )
                        media_url = supabase.storage.from_("marketplace").get_public_url(file_name)
                    supabase.table("marketplace_listings").insert({
                        "user_id": user.id,
                        "title": title,
                        "description": description,
                        "price_kc": price,
                        "media_url": media_url,
                        "media_type": "image",
                        "created_at": datetime.now().isoformat(),
                        "is_active": True,
                        "status": "Disponible",
                        "sales_count": 0
                    }).execute()
                    st.success("Annonce ajoutée et disponible !")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur lors de la publication : {e}")

    st.subheader("Annonces récentes")
    listings = supabase.table("marketplace_listings").select(
        "*, profiles!inner(username)"
    ).eq("is_active", True).order("created_at", desc=True).execute()
    if not listings.data:
        st.info("Aucune annonce pour le moment.")
        return

    cols = st.columns(3)
    for i, listing in enumerate(listings.data):
        with cols[i % 3]:
            status = listing.get("status", "Disponible")
            color = "green" if status == "Disponible" else "red"
            st.markdown(f"### {listing['title']}")
            st.markdown(f":{color}[**[{status}]**]")
            if listing.get("media_url"):
                st.image(listing["media_url"], use_container_width=True)
            st.write(listing["description"][:100] + "..." if len(listing["description"]) > 100 else listing["description"])
            st.write(f"💰 **{listing['price_kc']:,.0f} KC**")
            st.caption(f"Vendeur : {listing['profiles']['username']}")

            if listing["user_id"] != user.id:
                if status == "Disponible":
                    if st.button(f"🛒 Acheter ({listing['price_kc']} KC)", key=f"buy_{listing['id']}"):
                        # Vérifier que le statut est toujours Disponible (pour éviter les achats concurrents)
                        current_listing = supabase.table("marketplace_listings").select("status").eq("id", listing["id"]).single().execute()
                        if current_listing.data and current_listing.data["status"] != "Disponible":
                            st.error("Cette annonce n'est plus disponible.")
                            st.rerun()

                        wallet_res = supabase.table("wallets").select("*").eq("user_id", user.id).execute()
                        if wallet_res.data:
                            buyer_wallet = wallet_res.data[0]
                            if buyer_wallet["kongo_balance"] >= listing["price_kc"]:
                                try:
                                    # Débiter l'acheteur
                                    new_buyer_balance = buyer_wallet["kongo_balance"] - listing["price_kc"]
                                    supabase.table("wallets").update({"kongo_balance": new_buyer_balance}).eq("user_id", user.id).execute()
                                    # Créditer le vendeur
                                    vendeur_wallet_res = supabase.table("wallets").select("kongo_balance").eq("user_id", listing["user_id"]).execute()
                                    if vendeur_wallet_res.data:
                                        new_seller_balance = vendeur_wallet_res.data[0]["kongo_balance"] + listing["price_kc"]
                                        supabase.table("wallets").update({"kongo_balance": new_seller_balance}).eq("user_id", listing["user_id"]).execute()
                                    # Mettre à jour l'annonce
                                    new_sales_count = listing.get("sales_count", 0) + 1
                                    supabase.table("marketplace_listings").update({
                                        "status": "Vendu",
                                        "sales_count": new_sales_count
                                    }).eq("id", listing["id"]).execute()
                                    # Message automatique
                                    msg_text = f"🚨 ACHAT : Je suis intéressé par '{listing['title']}'. Le paiement de {listing['price_kc']} KC a été transféré sur votre compte."
                                    encrypted_msg = encrypt_text(msg_text)
                                    supabase.table("messages").insert({
                                        "sender": user.id,
                                        "recipient": listing["user_id"],
                                        "text": encrypted_msg,
                                        "created_at": datetime.now().isoformat()
                                    }).execute()
                                    st.success("✅ Transaction terminée ! Le vendeur a été notifié.")
                                    time.sleep(1.5)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erreur transactionnelle : {e}")
                            else:
                                st.error("Solde KC insuffisant.")
                        else:
                            st.error("Portefeuille introuvable.")
                else:
                    st.button("❌ Déjà Vendu", disabled=True, key=f"sold_{listing['id']}")
            else:
                st.info(f"📊 {listing.get('sales_count', 0)} client(s) sur cette annonce")

def wallet_page():
    st.header("💰 Mon Wallet")
    wallet = supabase.table("wallets").select("*").eq("user_id", user.id).execute()
    if not wallet.data:
        user_profile = supabase.table("profiles").select("role").eq("user_id", user.id).single().execute()
        is_admin_user = user_profile.data["role"] == "admin" if user_profile.data else False
        supabase.table("wallets").insert({
            "user_id": user.id,
            "kongo_balance": 100_000_000.0 if is_admin_user else 0.0,
            "total_mined": 0.0,
            "last_reward_at": datetime.now().isoformat()
        }).execute()
        wallet = supabase.table("wallets").select("*").eq("user_id", user.id).execute()
    wallet_data = wallet.data[0]
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Solde KC", f"{wallet_data['kongo_balance']:,.0f} KC")
    with col2:
        st.metric("Total miné", f"{wallet_data['total_mined']:,.0f} KC")

    if st.button("⛏️ Miner (récompense quotidienne)"):
        try:
            last_str = wallet_data["last_reward_at"]
            if last_str.endswith("Z"):
                last_str = last_str.replace("Z", "+00:00")
            last = datetime.fromisoformat(last_str)
            now = datetime.now()
            delta = now - last
            if delta.total_seconds() > 86400:
                new_balance = wallet_data["kongo_balance"] + 10
                new_mined = wallet_data["total_mined"] + 10
                supabase.table("wallets").update({
                    "kongo_balance": new_balance,
                    "total_mined": new_mined,
                    "last_reward_at": now.isoformat()
                }).eq("user_id", user.id).execute()
                st.success("+10 KC minés !")
                st.rerun()
            else:
                reste = 86400 - delta.total_seconds()
                st.warning(f"Prochain minage dans {int(reste//3600)}h {int((reste%3600)//60)}m.")
        except Exception as e:
            st.error(f"Erreur lors du minage : {e}")

    st.divider()
    st.subheader("📜 Activité récente")
    st.info("L'historique détaillé des transactions Marketplace sera bientôt disponible.")

def settings_page():
    st.header("⚙️ Paramètres")
    PREMIUM_PRICE = 10000.0

    sub = supabase.table("subscriptions").select("*").eq("user_id", user.id).execute()
    if sub.data:
        plan = sub.data[0]["plan_type"]
        expires = sub.data[0].get("expires_at")
        st.info(f"Plan actuel : **{plan}**" + (f" (expire le {expires[:10]})" if expires else ""))
    else:
        st.info("Plan actuel : **Gratuit**")

    if st.button("Passer à Premium (10 000 KC)"):
        wallet_res = supabase.table("wallets").select("*").eq("user_id", user.id).execute()
        if wallet_res.data:
            wallet_data = wallet_res.data[0]
            current_balance = wallet_data["kongo_balance"]
            if current_balance >= PREMIUM_PRICE:
                try:
                    new_balance = current_balance - PREMIUM_PRICE
                    supabase.table("wallets").update({
                        "kongo_balance": new_balance
                    }).eq("user_id", user.id).execute()

                    supabase.table("subscriptions").insert({
                        "user_id": user.id,
                        "plan_type": "Premium",
                        "activated_at": datetime.now().isoformat(),
                        "expires_at": (datetime.now().replace(year=datetime.now().year+1)).isoformat(),
                        "is_active": True
                    }).execute()
                    st.success(f"Compte Premium activé ! {PREMIUM_PRICE:,.0f} KC ont été débités.")
                    time.sleep(2)
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur lors de la transaction : {e}")
            else:
                st.error(f"Solde insuffisant. Il vous manque {PREMIUM_PRICE - current_balance:,.0f} KC.")
        else:
            st.error("Portefeuille introuvable. Veuillez d'abord initialiser votre Wallet.")

    st.divider()
    st.subheader("Zone dangereuse")
    if st.button("Supprimer mon compte", type="primary"):
        st.warning("Fonction désactivée pour le moment.")

def admin_page():
    st.header("🛡️ Espace Administration")
    st.caption("Actions réservées à la modération -- utilisez‑les avec discernement.")
    tab1, tab2, tab3, tab4 = st.tabs(["Utilisateurs", "Posts signalés", "Logs d'action", "Crédits"])

    with tab1:
        st.subheader("Gestion des utilisateurs")
        users = supabase.table("profiles").select("id, username, role, created_at").execute()
        df_users = pd.DataFrame(users.data)
        st.dataframe(df_users)
        with st.form("change_role"):
            user_id = st.selectbox(
                "Sélectionner un utilisateur",
                options=df_users["id"],
                format_func=lambda x: df_users[df_users["id"] == x]["username"].values[0]
            )
            new_role = st.selectbox("Nouveau rôle", ["user", "admin", "moderator"])
            if st.form_submit_button("Appliquer"):
                supabase.table("profiles").update({"role": new_role}).eq("id", user_id).execute()
                st.success("Rôle mis à jour")
                st.cache_data.clear()
                st.rerun()

    with tab2:
        st.subheader("Posts signalés")
        posts = supabase.table("posts").select("*, profiles(username)").order("created_at", desc=True).limit(100).execute()
        for post in posts.data:
            with st.expander(f"Post de {post['profiles']['username']} -- {post['created_at'][:16]}"):
                st.write(post["text"])
                if post.get("media_path"):
                    file_url = get_signed_url("media", post["media_path"])
                    if file_url:
                        st.image(file_url, width=200)
                if st.button("🗑️ Supprimer ce post", key=f"del_{post['id']}"):
                    delete_post(post["id"])

    with tab3:
        st.subheader("Journal des actions")
        st.info("Fonctionnalité à venir : traçabilité des actions d'administration.")

    with tab4:
        st.subheader("Créditer un utilisateur")
        users = supabase.table("profiles").select("id, username").execute()
        user_options = {u["id"]: u["username"] for u in users.data}
        selected_user = st.selectbox(
            "Choisir un utilisateur",
            options=list(user_options.keys()),
            format_func=lambda x: user_options[x]
        )
        amount = st.number_input("Montant (KC)", min_value=0.0, step=1000.0, value=100_000_000.0)
        if st.button("Ajouter des KC"):
            wallet = supabase.table("wallets").select("*").eq("user_id", selected_user).execute()
            if wallet.data:
                new_balance = wallet.data[0]["kongo_balance"] + amount
                supabase.table("wallets").update({"kongo_balance": new_balance}).eq("user_id", selected_user).execute()
            else:
                supabase.table("wallets").insert({
                    "user_id": selected_user,
                    "kongo_balance": amount,
                    "total_mined": 0.0,
                    "last_reward_at": datetime.now().isoformat()
                }).execute()
            st.success(f"{amount:,.0f} KC ajoutés à {user_options[selected_user]}")

# =====================================================
# ROUTEUR PRINCIPAL
# =====================================================
if menu == "🌐 Feed":
    feed_page()
elif menu == "👤 Mon Profil":
    profile_page()
elif menu == "✉️ Messages":
    messages_page()
elif menu == "🏪 Marketplace":
    marketplace_page()
elif menu == "💰 Wallet":
    wallet_page()
elif menu == "⚙️ Paramètres":
    settings_page()
elif menu == "🛡️ Admin":
    admin_page()
