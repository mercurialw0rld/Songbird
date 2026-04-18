import os
from collections import OrderedDict

import dotenv
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_chroma import Chroma
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_cohere import CohereRerank
from vectordatabase import CHROMA_SETTINGS

dotenv.load_dotenv(dotenv_path=".env")

K_RETRIEVE = 20
K_AFTER_RERANK = 5
DEDUP_KEY_PRIMARY = "track_name"
DEDUP_KEY_FALLBACK = "tempo"
PERSIST_DIRECTORY = "vector_store/"
EMBEDDING_MODEL_NAME = "models/gemini-embedding-001"
LLM_MODEL = "gemini-3-pro-preview"
CHROMA_COLLECTION = "langchain"
_CHROMA_CACHE_MAX = 6
_chroma_by_google_key: "OrderedDict[str, Chroma]" = OrderedDict()


def _resolve_google_key(google_api_key: str | None) -> str | None:
    s = (google_api_key or "").strip()
    if s:
        return s
    v = (os.environ.get("GOOGLE_API_KEY") or "").strip()
    return v or None


def _resolve_cohere_key(cohere_api_key: str | None) -> str | None:
    s = (cohere_api_key or "").strip()
    if s:
        return s
    v = (os.environ.get("COHERE_API_KEY") or "").strip()
    return v or None


def _get_chroma(google_api_key: str) -> Chroma:
    if google_api_key in _chroma_by_google_key:
        _chroma_by_google_key.move_to_end(google_api_key)
        return _chroma_by_google_key[google_api_key]

    embeddings = GoogleGenerativeAIEmbeddings(
        model=EMBEDDING_MODEL_NAME,
        google_api_key=google_api_key,
    )
    store = Chroma(
        embedding_function=embeddings,
        collection_name=CHROMA_COLLECTION,
        collection_metadata={"hnsw:space": "cosine"},
        client_settings=CHROMA_SETTINGS,
    )
    _chroma_by_google_key[google_api_key] = store
    _chroma_by_google_key.move_to_end(google_api_key)
    while len(_chroma_by_google_key) > _CHROMA_CACHE_MAX:
        _chroma_by_google_key.popitem(last=False)
    return store


def _get_base_retriever(google_api_key: str, k=K_RETRIEVE):
    vector_store = _get_chroma(google_api_key)
    return vector_store.as_retriever(
        search_type="similarity_score_threshold",
        search_kwargs={"k": k, "score_threshold": 0.3},
    )


def _deduplicate_documents(documents, key_primary=DEDUP_KEY_PRIMARY, key_fallback=DEDUP_KEY_FALLBACK):
    seen = set()
    unique = []
    for doc in documents:
        raw_id = doc.metadata.get(key_primary) or doc.metadata.get(key_fallback)
        doc_id = raw_id if raw_id else doc.page_content[:80]
        if doc_id in seen:
            continue
        seen.add(doc_id)
        unique.append(doc)
    return unique


def _rerank_documents(query, documents, cohere_api_key: str, top_n=K_AFTER_RERANK):
    if not documents:
        return []
    compressor = CohereRerank(
        top_n=top_n,
        model="rerank-english-v3.0",
        cohere_api_key=cohere_api_key,
    )
    compressed = compressor.compress_documents(documents, query)
    return list(compressed)


def retrieve_and_rerank(
    query: str,
    k_retrieve=K_RETRIEVE,
    k_rerank=K_AFTER_RERANK,
    google_api_key: str | None = None,
    cohere_api_key: str | None = None,
    popularity_mode: str = "any",
    popularity_threshold: int = 60,
):
    g = _resolve_google_key(google_api_key)
    c = _resolve_cohere_key(cohere_api_key)
    if not g:
        raise ValueError(
            "Missing Google API key: set it in the web API panel or set GOOGLE_API_KEY in .env."
        )
    if not c:
        raise ValueError(
            "Missing Cohere API key: set it in the web API panel or set COHERE_API_KEY in .env."
        )

    base_retriever = _get_base_retriever(g, k=k_retrieve)
    raw_docs = base_retriever.invoke(query)
    if not raw_docs:
        return []

    unique_docs = _deduplicate_documents(raw_docs)
    filtered_docs = _filter_by_popularity(unique_docs, popularity_mode, popularity_threshold)
    reranked = _rerank_documents(query, filtered_docs, c, top_n=k_rerank)
    return reranked


NO_MATCH_MESSAGE = (
    "I couldn't find tracks that match what you described. "
    "Try other moods, genres, or a bit more detail."
)


def _parse_track_artist_from_content(page_content: str) -> tuple[str, str]:
    name, artist = "", ""
    for line in (page_content or "").split("\n"):
        if line.startswith("Track: "):
            name = line.removeprefix("Track: ").strip()
        elif line.startswith("Artist: "):
            artist = line.removeprefix("Artist: ").strip()
    return name, artist


def _parse_popularity_from_content(page_content: str) -> int | None:
    for line in (page_content or "").split("\n"):
        if line.startswith("Popularity: "):
            raw = line.removeprefix("Popularity: ").strip()
            try:
                return int(float(raw))
            except Exception:
                return None
    return None


def _doc_popularity(doc) -> int | None:
    meta = doc.metadata or {}
    p = meta.get("track_popularity")
    if p is None or p == "":
        return _parse_popularity_from_content(doc.page_content)
    try:
        return int(p)
    except Exception:
        return _parse_popularity_from_content(doc.page_content)


def _filter_by_popularity(docs, mode: str, threshold: int):
    """
    mode:
      - any: no filtering
      - known: keep tracks with popularity >= threshold
      - unknown: keep tracks with popularity <= threshold
    """
    mode = (mode or "any").strip().lower()
    if mode not in {"any", "known", "unknown"}:
        mode = "any"
    thr = max(0, min(100, int(threshold)))
    if mode == "any":
        return list(docs)

    out = []
    for d in docs:
        p = _doc_popularity(d)
        if p is None:
            continue
        if mode == "known" and p >= thr:
            out.append(d)
        elif mode == "unknown" and p <= thr:
            out.append(d)
    return out


def _doc_to_track_preview(doc) -> dict:
    meta = doc.metadata or {}
    name = (meta.get("track_name") or "").strip()
    artist = (meta.get("track_artist") or "").strip()
    if not name or not artist:
        n, a = _parse_track_artist_from_content(doc.page_content)
        name = name or n or "—"
        artist = artist or a or "—"
    uri = (meta.get("uri") or "").strip()
    tid = (meta.get("track_id") or meta.get("id") or "").strip()
    href = ""
    if uri.startswith("spotify:track:") and len(uri) > 14:
        href = f"https://open.spotify.com/track/{uri.split(':')[-1]}"
    elif tid:
        href = f"https://open.spotify.com/track/{tid}"
    return {
        "track_name": name,
        "track_artist": artist,
        "track_popularity": _doc_popularity(doc),
        "playlist_genre": (meta.get("playlist_genre") or "").strip(),
        "playlist_subgenre": (meta.get("playlist_subgenre") or "").strip(),
        "spotify_url": href,
        "snippet": doc.page_content[:320] + ("…" if len(doc.page_content) > 320 else ""),
    }


def _llm_recommend_from_docs(query: str, relevant_docs, google_api_key: str) -> str:
    context = "\n\n---\n\n".join(doc.page_content for doc in relevant_docs)
    model = ChatGoogleGenerativeAI(
        model="gemini-3-pro-preview",
        temperature=1.0,
        max_tokens=None,
        timeout=None,
        max_retries=2,
        google_api_key=google_api_key,
    )
    system_content = (
        "You are a music assistant. The user receives tracks pre-selected by a search system. "
        "Reply in the same language the user writes in. From each track's description, explain why it fits "
        "their taste and what they might like about it. Be brief and friendly. If a row looks incoherent "
        "(e.g. wrong content), pick another relevant track from the list—do not invent songs that are not in the list.\n\n"
        "Relevant tracks:\n" + context
    )
    messages = [
        ("system", system_content),
        ("human", query),
    ]
    response = model.invoke(messages)
    return _stringify_llm_content(response.content)


def _stringify_llm_content(content):
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                t = block.get("text")
                if t is not None:
                    parts.append(str(t))
        return "\n".join(parts).strip() if parts else repr(content)
    return str(content)


def recommend_songs(
    query: str,
    google_api_key: str | None = None,
    cohere_api_key: str | None = None,
    popularity_mode: str = "any",
    popularity_threshold: int = 60,
):
    relevant_docs = retrieve_and_rerank(
        query,
        google_api_key=google_api_key,
        cohere_api_key=cohere_api_key,
        popularity_mode=popularity_mode,
        popularity_threshold=popularity_threshold,
    )
    if not relevant_docs:
        return NO_MATCH_MESSAGE
    g = _resolve_google_key(google_api_key)
    assert g  # retrieve_and_rerank already validated
    return _llm_recommend_from_docs(query, relevant_docs, g)


def recommend_songs_payload(
    query: str,
    google_api_key: str | None = None,
    cohere_api_key: str | None = None,
    popularity_mode: str = "any",
    popularity_threshold: int = 60,
) -> dict:
    """API payload: LLM reply text + reranked track cards."""
    relevant_docs = retrieve_and_rerank(
        query,
        google_api_key=google_api_key,
        cohere_api_key=cohere_api_key,
        popularity_mode=popularity_mode,
        popularity_threshold=popularity_threshold,
    )
    if not relevant_docs:
        return {"reply": NO_MATCH_MESSAGE, "tracks": []}
    g = _resolve_google_key(google_api_key)
    assert g
    reply = _llm_recommend_from_docs(query, relevant_docs, g)
    return {
        "reply": reply,
        "tracks": [_doc_to_track_preview(d) for d in relevant_docs],
    }


if __name__ == "__main__":
    print("Songbird — RAG recommendations (retrieve + dedup + rerank + LLM)\n")
    user_query = input("Describe your taste or the kind of track you want: ").strip()
    if not user_query:
        print("Empty input. Example: 'High-energy dance with 80s synths'")
    else:
        print("\nRetrieving and reranking...")
        answer = recommend_songs(user_query)
        print("\nRecommendation:\n")
        print(answer)