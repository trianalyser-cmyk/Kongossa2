# dissipation_phi.py
import streamlit as st
import psutil
import time
import random
import gc
import hashlib
from datetime import datetime, timedelta
import pandas as pd
from memory_phi import (
    supabase, user, profile, is_admin, tst_params,
    measure_phi_m, memory, compress_log, decompress_log,
    get_signed_url, get_user_badge, logout, encrypt_text, decrypt_text
)
from coherence_phi import (
    coherence, predictor, get_post_stats, like_post, add_comment,
    delete_post, process_emoji_payment, send_message, buy_listing,
    search_similar
)

# =====================================================
# MESURE DE LA DISSIPATION (ΦD)
# =====================================================
def measure_phi_d():
    cpu = psutil.cpu_percent(interval=0.1) / 100.0
    latency = random.uniform(0.1, 0.5) / 1000.0
    return min(cpu + latency, 1.0)

class DissipationRegulator:
    def __init__(self):
        self.phi_d_threshold = 0.7
        self.low_power_mode = False
    
    def update(self):
        phi_d = measure_phi_d()
        phi_m = measure_phi_m()
        phi_c = coherence.get_phi_c()
        if phi_m + phi_d > phi_c:
            self.low_power_mode = True
            st.warning("⚠️ Mode basse énergie activé")
        else:
            self.low_power_mode = False
        return self.low_power_mode

regulator = DissipationRegulator()

def stability_control(func):
    def wrapper(*args, **kwargs):
        low_power = regulator.update()
        kwargs["low_power"] = low_power
        return func(*args, **kwargs)
    return wrapper

# =====================================================
# PAGE FEED (simplifiée, sans rerun excessifs)
# =====================================================
@stability_control
def feed_page(low_power=False):
    st.header("🌐 Fil d'actualité")
    predictor.add_event("Feed")
    predictor.prefetch()

    # Création de post
    with st.expander("✍️ Créer un post"):
        with st.form("new_post", clear_on_submit=True):
            post_text = st.text_area("Quoi de neuf ?")
            media_file = st.file_uploader("Média", type=["png", "jpg", "jpeg", "mp4", "mp3", "wav"])
            if st.form_submit_button("Publier"):
                if post_text or media_file:
                    if media_file and media_file.size > 50 * 1024 * 1024:
                        st.error("Fichier trop volumineux (max 50 Mo)")
                    else:
                        try:
                            # Upload média si présent
                            media_path = None
                            media_type = None
                            if media_file:
                                ext = media_file.name.split(".")[-1]
                                file_name = f"posts/{user.id}/{uuid.uuid4()}.{ext}"
                                content_type = f"image/{ext}" if ext in ["jpg","jpeg","png"] else f"video/{ext}" if ext=="mp4" else f"audio/{ext}"
                                supabase.storage.from_("media").upload(
                                    path=file_name,
                                    file=media_file.getvalue(),
                                    file_options={"content-type": content_type}
                                )
                                media_path = file_name
                                media_type = content_type
                            # Insertion du post
                            post_data = {
                                "user_id": user.id,
                                "text": post_text,
                                "media_path": media_path,
                                "media_type": media_type,
                                "created_at": datetime.now().isoformat(),
                                "like_count": 0,
                                "comment_count": 0,
                                "tst_rank_score": 0.0
                            }
                            supabase.table("posts").insert(post_data).execute()
                            st.success("Post publié !")
                            st.rerun()  # seul rerun pour actualiser le feed
                        except Exception as e:
                            st.error(f"Erreur : {e}")

    # Chargement des posts (optimisé)
    limit = 10 if low_power else 30
    try:
        posts = supabase.table("posts").select(
            "*, profiles!inner(username, profile_pic)"
        ).order("created_at", desc=True).limit(limit).execute().data
    except Exception:
        posts = []

    if not posts:
        st.info("Aucun post pour le moment.")
        return

    for post in posts:
        with st.container():
            col1, col2 = st.columns([1, 20])
            with col1:
                pic = post["profiles"].get("profile_pic") or "https://via.placeholder.com/40"
                st.image(pic, width=40)
            with col2:
                st.markdown(f"**{post['profiles']['username']}** · {post['created_at'][:10]}")
                st.write(post["text"])

                if post.get("media_path") and not low_power:
                    url = get_signed_url("media", post["media_path"])
                    if url:
                        if "image" in post.get("media_type",""):
                            st.image(url)
                        elif "video" in post.get("media_type",""):
                            st.video(url)
                        elif "audio" in post.get("media_type",""):
                            st.audio(url)

                stats = get_post_stats(post["id"])
                st.markdown(f"❤️ {stats['likes']} | 💬 {stats['comments']} | 🔥 {stats['reactions']}")

                # Boutons d'action sans rerun (sauf like/comment)
                cols = st.columns(5)
                with cols[0]:
                    if st.button("❤️", key=f"like_{post['id']}"):
                        like_post(post["id"])
                with cols[1]:
                    with st.expander("💬"):
                        # Afficher commentaires existants
                        try:
                            comments = supabase.table("comments").select(
                                "*, profiles(username)"
                            ).eq("post_id", post["id"]).order("created_at").execute().data
                            for c in comments:
                                st.markdown(f"**{c['profiles']['username']}** : {c['text']}")
                        except:
                            pass
                        # Formulaire pour nouveau commentaire
                        with st.form(key=f"comment_form_{post['id']}"):
                            new_c = st.text_input("Votre commentaire")
                            if st.form_submit_button("Envoyer"):
                                add_comment(post["id"], new_c)
                with cols[2]:
                    if st.button("🔥 10", key=f"fire_{post['id']}"):
                        process_emoji_payment(post["id"], post["user_id"], "🔥")
                with cols[3]:
                    if st.button("💎 50", key=f"diamond_{post['id']}"):
                        process_emoji_payment(post["id"], post["user_id"], "💎")
                with cols[4]:
                    if st.button("👑 100", key=f"crown_{post['id']}"):
                        process_emoji_payment(post["id"], post["user_id"], "👑")

                if post["user_id"] == user.id or is_admin():
                    if st.button("🗑️ Supprimer", key=f"del_{post['id']}"):
                        delete_post(post["id"])
            st.divider()

# =====================================================
# PAGE TOKTOK (simplifiée, sans panélistes)
# =====================================================
@stability_control
def ttu_vertical_feed(low_power=False):
    st.subheader("🎵 TokTok - Flux vertical")

    # Récupération des panneaux actifs
    try:
        panels = supabase.table("ttu_panels").select(
            "*, profiles!creator_id(username, profile_pic)"
        ).eq("is_live", True).order("current_stability", desc=True).limit(10).execute().data
    except Exception:
        panels = []

    if not panels:
        st.info("Aucun panneau actif.")
        return

    # Navigation simple
    if "panel_index" not in st.session_state:
        st.session_state.panel_index = 0

    col1, col2, col3 = st.columns([1, 10, 1])
    with col1:
        if st.button("⬆️") and st.session_state.panel_index > 0:
            st.session_state.panel_index -= 1
            st.rerun()
    with col3:
        if st.button("⬇️") and st.session_state.panel_index < len(panels)-1:
            st.session_state.panel_index += 1
            st.rerun()

    panel = panels[st.session_state.panel_index]

    # Affichage du panneau
    st.markdown(f"## {panel['title']}")
    st.markdown(f"Créé par {panel['profiles']['username']}")
    st.metric("Stabilité", f"{panel.get('current_stability',1.0):.2f}")

    # Chat du panneau (fragmenté)
    render_chat_fragment(panel['id'])

@st.fragment
def render_chat_fragment(panel_id):
    """Zone de chat isolée (se re-rend seule)."""
    # Afficher les messages
    try:
        msgs = supabase.table("messages").select("sender, text, created_at").eq("panel_id", panel_id).order("created_at", desc=True).limit(20).execute().data
        if msgs:
            sender_ids = list(set(m["sender"] for m in msgs))
            profiles = supabase.table("profiles").select("id, username").in_("id", sender_ids).execute().data
            profile_dict = {p["id"]: p["username"] for p in profiles}
            for msg in reversed(msgs):
                username = profile_dict.get(msg["sender"], "Inconnu")
                decrypted = decrypt_text(msg.get("text", ""))
                with st.chat_message("user"):
                    st.markdown(f"**{username}**: {decrypted}")
        else:
            st.info("Aucun message")
    except Exception:
        st.warning("Erreur de chargement")

    # Formulaire pour nouveau message
    with st.form(key=f"toktok_msg_{panel_id}"):
        new_msg = st.text_input("Votre message")
        if st.form_submit_button("Envoyer"):
            if new_msg.strip():
                encrypted = encrypt_text(new_msg)
                supabase.table("messages").insert({
                    "sender": user.id,
                    "panel_id": panel_id,
                    "text": encrypted,
                    "created_at": datetime.now().isoformat()
                }).execute()
                st.rerun(scope="fragment")  # ne rerun que ce fragment

# =====================================================
# AUTRES PAGES (à adapter de même, sans rerun inutiles)
# =====================================================
def profile_page():
    st.header("👤 Mon Profil")
    # ... (code existant mais sans rerun multiples)

def messages_page():
    st.header("✉️ Messagerie")
    # ... (à simplifier)

def marketplace_page():
    st.header("🏪 Marketplace")
    # ... (à simplifier)

def wallet_page():
    st.header("💰 Wallet")
    # ... (inchangé mais sans rerun)

def settings_page():
    st.header("⚙️ Paramètres")
    # ... (inchangé)

def admin_page():
    st.header("🛡️ Admin")
    # ... (inchangé)

# =====================================================
# ROUTAGE
# =====================================================
def run():
    st.sidebar.image("https://via.placeholder.com/150x50?text=GEN-Z", width=150)
    st.sidebar.write(f"Connecté : **{profile['username']}**")
    if is_admin():
        st.sidebar.markdown("🔑 Administrateur")

    menu_options = ["🎵 TokTok", "🌐 Feed", "👤 Profil", "✉️ Messages", "🏪 Marketplace", "💰 Wallet", "⚙️ Paramètres"]
    if is_admin():
        menu_options.append("🛡️ Admin")
    menu = st.sidebar.radio("Navigation", menu_options, key="main_menu")

    if st.sidebar.button("🚪 Déconnexion"):
        logout()

    if menu == "🎵 TokTok":
        ttu_vertical_feed()
    elif menu == "🌐 Feed":
        feed_page()
    elif menu == "👤 Profil":
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
