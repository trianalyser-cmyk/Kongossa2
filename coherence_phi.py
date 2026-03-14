# coherence_phi.py
import streamlit as st
import numpy as np
import time
from datetime import datetime
from sklearn.metrics.pairwise import cosine_similarity
from memory_phi import supabase, encrypt_text, decrypt_text, user, measure_phi_m, memory

# =====================================================
# MESURE DE LA COHÉRENCE (ΦC)
# =====================================================
class CoherenceMeter:
    def __init__(self):
        self.total_queries = 0
        self.useful_queries = 0
    
    def record_query(self, useful=True):
        self.total_queries += 1
        if useful:
            self.useful_queries += 1
    
    def get_phi_c(self):
        if self.total_queries == 0:
            return 1.0
        return self.useful_queries / self.total_queries

coherence = CoherenceMeter()

# =====================================================
# MOTEUR DE PRÉDICTION (préchargement intelligent)
# =====================================================
class Predictor:
    """Prédit la prochaine action de l'utilisateur à partir de l'historique."""
    
    def __init__(self):
        self.history = []  # liste des pages visitées
    
    def add_event(self, page):
        self.history.append(page)
        if len(self.history) > 20:
            self.history.pop(0)
    
    def predict_next(self):
        """Retourne la page la plus probable."""
        if not self.history:
            return None
        # Algorithme simple : dernière page visitée
        return self.history[-1]
    
    def prefetch(self):
        """Précharge les données de la page prédite."""
        next_page = self.predict_next()
        if next_page == "Feed":
            # Précharger les posts récents
            try:
                data = supabase.table("posts").select("id, text").limit(10).execute()
                memory.store("prefetched_posts", data.data, level="cache")
                coherence.record_query(useful=True)
            except:
                coherence.record_query(useful=False)
        elif next_page == "Messages":
            # Précharger les contacts récents
            try:
                data = supabase.table("messages").select("recipient").eq("sender", user.id).limit(5).execute()
                memory.store("prefetched_contacts", data.data, level="cache")
                coherence.record_query(useful=True)
            except:
                coherence.record_query(useful=False)
        # etc.

predictor = Predictor()

# =====================================================
# INDEXATION VECTORIELLE (recherche sémantique)
# =====================================================
def embed_text(text: str) -> list:
    """Génère un embedding pour un texte."""
    # Simulation : hash -> vecteur pseudo-aléatoire
    hash_val = int(hashlib.sha256(text.encode()).hexdigest(), 16)
    np.random.seed(hash_val % 2**32)
    return np.random.randn(384).astype(np.float32).tolist()

def search_similar(query: str, table: str, column: str, top_k: int = 5):
    """Recherche les entrées les plus similaires via pgvector (simulation)."""
    # Note : nécessite pgvector et une colonne embedding
    # Ici on simule avec une requête classique
    try:
        # Récupérer toutes les entrées (limité pour l'exemple)
        data = supabase.table(table).select("id, text").limit(100).execute()
        if not data.data:
            return []
        # Calculer similarité cosinus
        query_emb = np.array(embed_text(query))
        similarities = []
        for item in data.data:
            # Si l'item a un embedding stocké, l'utiliser; sinon en générer un
            item_emb = np.array(embed_text(item.get("text", "")))
            sim = cosine_similarity([query_emb], [item_emb])[0][0]
            similarities.append((sim, item))
        similarities.sort(key=lambda x: -x[0])
        return [item for sim, item in similarities[:top_k]]
    except Exception as e:
        st.error(f"Erreur recherche : {e}")
        return []

# =====================================================
# INTERACTIONS SOCIALES (avec mise à jour de cohérence)
# =====================================================
def get_post_stats(post_id):
    try:
        likes = supabase.table("likes").select("*", count="exact").eq("post_id", post_id).execute()
        comments = supabase.table("comments").select("*", count="exact").eq("post_id", post_id).execute()
        reactions = supabase.table("reactions").select("*", count="exact").eq("post_id", post_id).execute()
        coherence.record_query(useful=True)
        return {
            "likes": likes.count or 0,
            "comments": comments.count or 0,
            "reactions": reactions.count or 0
        }
    except Exception:
        coherence.record_query(useful=False)
        return {"likes": 0, "comments": 0, "reactions": 0}

def like_post(post_id):
    try:
        supabase.table("likes").insert({"post_id": post_id, "user_id": user.id}).execute()
        post = supabase.table("posts").select("like_count").eq("id", post_id).execute()
        if post.data:
            new_count = post.data[0]["like_count"] + 1
            supabase.table("posts").update({"like_count": new_count}).eq("id", post_id).execute()
        # Mise à jour de la dissipation sera faite dans dissipation_phi
        st.success("👍 Like ajouté !")
        time.sleep(0.5)
        st.rerun()
    except Exception:
        st.error("Vous avez déjà liké ce post.")

def add_comment(post_id, text):
    if not text.strip():
        st.warning("Commentaire vide.")
        return
    try:
        supabase.table("comments").insert({"post_id": post_id, "user_id": user.id, "text": text}).execute()
        post = supabase.table("posts").select("comment_count").eq("id", post_id).execute()
        if post.data:
            new_count = post.data[0]["comment_count"] + 1
            supabase.table("posts").update({"comment_count": new_count}).eq("id", post_id).execute()
        st.success("💬 Commentaire ajouté")
        time.sleep(0.5)
        st.rerun()
    except Exception as e:
        st.error(f"Erreur : {e}")

def delete_post(post_id):
    try:
        post = supabase.table("posts").select("media_path").eq("id", post_id).execute()
        if post.data and post.data[0].get("media_path"):
            supabase.storage.from_("media").remove([post.data[0]["media_path"]])
        supabase.table("posts").delete().eq("id", post_id).execute()
        st.success("Post supprimé")
        st.rerun()
    except Exception as e:
        st.error(f"Erreur : {e}")

EMOJI_HIERARCHY = {
    "🔥": {"cost": 10, "share": 8},
    "💎": {"cost": 50, "share": 40},
    "👑": {"cost": 100, "share": 80}
}

def process_emoji_payment(post_id, author_id, emoji_type):
    cost = EMOJI_HIERARCHY[emoji_type]["cost"]
    share = EMOJI_HIERARCHY[emoji_type]["share"]
    try:
        wallet = supabase.table("wallets").select("kongo_balance").eq("user_id", user.id).execute()
        if not wallet.data or wallet.data[0]["kongo_balance"] < cost:
            st.error("Solde insuffisant.")
            return
        new_bal = wallet.data[0]["kongo_balance"] - cost
        supabase.table("wallets").update({"kongo_balance": new_bal}).eq("user_id", user.id).execute()
        author_wallet = supabase.table("wallets").select("kongo_balance").eq("user_id", author_id).execute()
        if author_wallet.data:
            new_author_bal = author_wallet.data[0]["kongo_balance"] + share
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
        st.error(f"Erreur : {e}")

def send_message(recipient_id, text):
    if not text.strip():
        return
    encrypted = encrypt_text(text)
    supabase.table("messages").insert({
        "sender": user.id,
        "recipient": recipient_id,
        "text": encrypted,
        "created_at": datetime.now().isoformat()
    }).execute()

def buy_listing(listing_id, seller_id, price):
    try:
        listing = supabase.table("marketplace_listings").select("status").eq("id", listing_id).single().execute()
        if listing.data and listing.data["status"] != "Disponible":
            st.error("Annonce déjà vendue.")
            return False
        buyer_wallet = supabase.table("wallets").select("kongo_balance").eq("user_id", user.id).execute()
        if not buyer_wallet.data or buyer_wallet.data[0]["kongo_balance"] < price:
            st.error("Solde insuffisant.")
            return False
        new_buyer_bal = buyer_wallet.data[0]["kongo_balance"] - price
        supabase.table("wallets").update({"kongo_balance": new_buyer_bal}).eq("user_id", user.id).execute()
        seller_wallet = supabase.table("wallets").select("kongo_balance").eq("user_id", seller_id).execute()
        if seller_wallet.data:
            new_seller_bal = seller_wallet.data[0]["kongo_balance"] + price
            supabase.table("wallets").update({"kongo_balance": new_seller_bal}).eq("user_id", seller_id).execute()
        supabase.table("marketplace_listings").update({
            "status": "Vendu",
            "sales_count": supabase.table("marketplace_listings").select("sales_count").eq("id", listing_id).execute().data[0]["sales_count"] + 1
        }).eq("id", listing_id).execute()
        msg = f"🚨 ACHAT : {listing['title']} a été acheté. {price} KC transférés."
        send_message(seller_id, msg)
        st.success("Transaction réussie !")
        return True
    except Exception as e:
        st.error(f"Erreur transaction : {e}")
        return False
