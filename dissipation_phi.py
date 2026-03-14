# dissipation_phi.py
import streamlit as st
import psutil
import time
import random
import gc
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
    """Retourne ΦD = cpu_load + network_latency (normalisé)."""
    cpu = psutil.cpu_percent(interval=0.1) / 100.0
    # Simule une latence réseau (à remplacer par une vraie mesure)
    latency = random.uniform(0.1, 0.5) / 1000.0  # en ms, normalisé
    return min(cpu + latency, 1.0)

# =====================================================
# RÉGULATEUR DE DISSIPATION
# =====================================================
class DissipationRegulator:
    def __init__(self):
        self.phi_d_threshold = 0.7
        self.low_power_mode = False
    
    def update(self):
        phi_d = measure_phi_d()
        phi_m = measure_phi_m()
        phi_c = coherence.get_phi_c()
        # Condition de stabilité : phi_m + phi_d < phi_c
        if phi_m + phi_d > phi_c:
            self.low_power_mode = True
            st.warning("⚠️ Mode basse énergie activé (stabilité compromise)")
        else:
            self.low_power_mode = False
        return self.low_power_mode

regulator = DissipationRegulator()

def stability_control(func):
    """Décorateur pour adapter l'affichage selon le mode."""
    def wrapper(*args, **kwargs):
        low_power = regulator.update()
        kwargs["low_power"] = low_power
        return func(*args, **kwargs)
    return wrapper

# =====================================================
# GESTION ENTROPIQUE DES LOGS
# =====================================================
def clean_old_logs():
    """Supprime les logs anciens ou les compresse."""
    try:
        # Récupérer les logs de la table admin_logs
        logs = supabase.table("admin_logs").select("id, details, created_at").execute()
        if not logs.data:
            return
        for log in logs.data:
            age = (datetime.now() - datetime.fromisoformat(log["created_at"])).days
            if age > 30:
                # Supprimer les logs de plus de 30 jours
                supabase.table("admin_logs").delete().eq("id", log["id"]).execute()
            elif age > 7:
                # Compresser les logs de 7 à 30 jours
                compressed = compress_log(str(log["details"]))
                supabase.table("admin_logs").update({
                    "details": compressed
                }).eq("id", log["id"]).execute()
    except Exception:
        pass

# =====================================================
# OPTIMISATION RÉSEAU
# =====================================================
def optimized_select(table, columns="*", limit=50, **filters):
    """Exécute une requête avec sélection limitée des colonnes."""
    query = supabase.table(table).select(columns)
    for k, v in filters.items():
        query = query.eq(k, v)
    if limit:
        query = query.limit(limit)
    return query.execute()

# =====================================================
# PAGES (avec intégration des mesures)
# =====================================================
@stability_control
def feed_page(low_power=False):
    st.header("🌐 Fil d'actualité")
    predictor.add_event("Feed")
    predictor.prefetch()

    with st.expander("✍️ Créer un post", expanded=False):
        with st.form("new_post"):
            post_text = st.text_area("Quoi de neuf ?")
            media_file = st.file_uploader("Média", type=["png", "jpg", "jpeg", "mp4", "mp3", "wav"])
            submitted = st.form_submit_button("Publier")
            if submitted and (post_text or media_file):
                if media_file and media_file.size > 50 * 1024 * 1024:
                    st.error("Fichier trop volumineux (max 50 Mo).")
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
                        "created_at": datetime.now().isoformat(),
                        "like_count": 0,
                        "comment_count": 0,
                        "tst_rank_score": 0.0
                    }
                    post_res = supabase.table("posts").insert(post_data).execute()
                    post_id = post_res.data[0]["id"]

                    # Métadonnée spectrale
                    supabase.table("ttu_spectral_metadata").insert({
                        "post_id": post_id,
                        "spectral_m_hash": hashlib.sha256((post_text or "").encode()).hexdigest(),
                        "coherence_vectors": {},
                        "spectral_density": 1.0,
                        "dissipation_rate": 0.05,
                        "entropy_limit": 0.95
                    }).execute()

                    st.success("Post publié !")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur : {e}")

    # Chargement des posts avec optimisation
    limit = 10 if low_power else 50
    try:
        posts = optimized_select("posts", columns="*, profiles!inner(username, profile_pic)", limit=limit).data
    except Exception:
        posts = []

    if not posts:
        st.info("Aucun post pour le moment.")
        return

    for post in posts:
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

                if post.get("media_path") and not low_power:
                    file_url = get_signed_url("media", post["media_path"])
                    if file_url:
                        if post.get("media_type") and "image" in post["media_type"]:
                            st.image(file_url)
                        elif post.get("media_type") and "video" in post["media_type"]:
                            st.video(file_url)
                        elif post.get("media_type") and "audio" in post["media_type"]:
                            st.audio(file_url)

                stats = get_post_stats(post["id"])
                st.markdown(f"❤️ {stats['likes']} | 💬 {stats['comments']} | 🔥 {stats['reactions']}")

                col_a, col_b, col_c, col_d, col_e = st.columns([1, 1, 1, 1, 1])
                with col_a:
                    if st.button("❤️", key=f"like_{post['id']}"):
                        like_post(post["id"])
                with col_b:
                    with st.popover("💬"):
                        try:
                            comments = supabase.table("comments").select(
                                "*, profiles(username)"
                            ).eq("post_id", post["id"]).order("created_at").execute()
                            for c in comments.data:
                                st.markdown(f"**{c['profiles']['username']}** : {c['text']}")
                        except Exception:
                            st.warning("Erreur chargement commentaires")
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

                if post["user_id"] == user.id or is_admin():
                    if st.button("🗑️ Supprimer", key=f"del_{post['id']}"):
                        delete_post(post["id"])
            st.divider()

@stability_control
def ttu_vertical_feed(low_power=False):
    st.subheader("📷 Lancer mon Live")
    # Désactiver la caméra en mode basse énergie
    if not low_power:
        # webrtc_streamer(key="live-stream", ...) # à décommenter si installé
        st.info("Caméra disponible (simulée)")
    else:
        st.warning("Caméra désactivée (mode basse énergie)")

    # Panneaux actifs
    try:
        panels = supabase.table("ttu_panels").select(
            "*, profiles!creator_id(username, profile_pic)"
        ).eq("is_live", True).order("current_stability", desc=True).limit(10).execute()
        items = [{"type": "panel", "data": p} for p in panels.data]
        random.shuffle(items)
    except Exception:
        items = []

    if not items:
        st.info("Aucun panneau actif.")
        return

    if "ttu_index" not in st.session_state:
        st.session_state.ttu_index = 0

    col1, col2, col3 = st.columns([1, 10, 1])
    with col1:
        if st.button("⬆️", key="prev_panel") and st.session_state.ttu_index > 0:
            st.session_state.ttu_index -= 1
            st.rerun()
    with col3:
        if st.button("⬇️", key="next_panel") and st.session_state.ttu_index < len(items) - 1:
            st.session_state.ttu_index += 1
            st.rerun()

    current = items[st.session_state.ttu_index]
    panel = current["data"]

    col_main, col_sidebar = st.columns([0.85, 0.15])
    with col_main:
        st.markdown(f"## {panel['title']}")
        st.markdown(f"Créé par {panel['profiles']['username']}")

        # Panélistes (simulés)
        st.markdown("**Panélistes**")
        panelist_cols = st.columns(3)
        panelists = [{"name": "User1", "mic": True}, {"name": "User2", "mic": False}, {"name": "User3", "mic": True}]
        for i, p in enumerate(panelists):
            with panelist_cols[i]:
                st.markdown(f"{'🎤' if p['mic'] else '🔇'} {p['name']}")

        # Chat
        render_chat(panel['id'])

    with col_sidebar:
        st.image(panel['profiles'].get('profile_pic') or "https://via.placeholder.com/100", width=80)
        st.metric("Stabilité", f"{panel.get('current_stability', 1.0):.2f}")
        if st.button("❤️ Like", key=f"like_panel_{panel['id']}"):
            st.info("Like (simulé)")
        with st.popover("🎁 Cadeau"):
            try:
                gifts = supabase.table("gift_definitions").select("*").order("kc_cost").execute()
                for g in gifts.data[:3]:
                    if st.button(f"{g['emoji']} {g['name']} ({int(g['kc_cost'])} KC)", key=f"gift_{g['id']}_{panel['id']}"):
                        # Traitement cadeau (simplifié)
                        st.success(f"Cadeau {g['name']} envoyé !")
            except Exception:
                st.error("Erreur cadeaux")

    # Formulaire commentaire
    with st.form(key=f"comment_form_{panel['id']}"):
        comment = st.text_input("Votre commentaire")
        if st.form_submit_button("Envoyer") and comment:
            encrypted = encrypt_text(comment)
            supabase.table("messages").insert({
                "sender": user.id,
                "panel_id": panel["id"],
                "text": encrypted,
                "created_at": datetime.now().isoformat()
            }).execute()
            st.rerun()

def render_chat(panel_id):
    try:
        msgs = supabase.table("messages").select("sender, text, created_at").eq("panel_id", panel_id).order("created_at", desc=True).limit(10).execute()
        if not msgs.data:
            st.info("Aucun message.")
            return
        sender_ids = list(set(m["sender"] for m in msgs.data))
        profiles = supabase.table("profiles").select("id, username").in_("id", sender_ids).execute()
        profile_dict = {p["id"]: p["username"] for p in profiles.data}
        for msg in reversed(msgs.data):
            username = profile_dict.get(msg["sender"], "Inconnu")
            decrypted = decrypt_text(msg.get("text", ""))
            with st.chat_message("user"):
                st.markdown(f"**{username}**: {decrypted}")
    except Exception:
        st.warning("Messages indisponibles.")

def profile_page():
    st.header("👤 Mon Profil")
    predictor.add_event("Profil")
    # ... (code existant, non reproduit pour brièveté)

def messages_page():
    st.header("✉️ Messagerie")
    predictor.add_event("Messages")
    # ... (code existant)

def marketplace_page():
    st.header("🏪 Marketplace")
    predictor.add_event("Marketplace")
    # ... (code existant)

def wallet_page():
    st.header("💰 Wallet")
    predictor.add_event("Wallet")
    # ... (code existant)

def settings_page():
    st.header("⚙️ Paramètres")
    # ... (code existant)

def admin_page():
    st.header("🛡️ Admin")
    # ... (code existant)

# =====================================================
# ROUTAGE
# =====================================================
def run():
    # Nettoyage périodique des logs (une fois par session)
    if "logs_cleaned" not in st.session_state:
        clean_old_logs()
        st.session_state.logs_cleaned = True

    st.sidebar.image("https://via.placeholder.com/150x50?text=GEN-Z", width=150)
    st.sidebar.write(f"Connecté : **{profile['username']}**")
    if is_admin():
        st.sidebar.markdown("🔑 Administrateur")

    menu_options = ["🎵 TokTok", "🌐 Feed", "👤 Profil", "✉️ Messages", "🏪 Marketplace", "💰 Wallet", "⚙️ Paramètres"]
    if is_admin():
        menu_options.append("🛡️ Admin")
    menu = st.sidebar.radio("Navigation", menu_options)

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
