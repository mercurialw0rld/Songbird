import pandas as pd
from langchain_core.documents import Document
from langchain_community.document_loaders import DirectoryLoader


class CSVLoader:
    def __init__(self, path):
        self.path = path
        self.file_path = path  # DirectoryLoader passes file_path kwarg

    def lazy_load(self):
        yield from self.read()

    def load(self):
        return self.read()

    def read(self):
        df = pd.read_csv(self.path)
        docs = []

        for _, row in df.iterrows():
            content_parts = []
            if pd.notna(row.get("track_name")):
                content_parts.append(f"Track: {row['track_name']}")
            if pd.notna(row.get("track_artist")):
                content_parts.append(f"Artist: {row['track_artist']}")
            if pd.notna(row.get("track_album_name")):
                content_parts.append(f"Album: {row['track_album_name']}")
            if pd.notna(row.get("playlist_name")):
                content_parts.append(f"Playlist: {row['playlist_name']}")
            if pd.notna(row.get("playlist_genre")):
                sub = row.get("playlist_subgenre")
                if pd.notna(sub):
                    content_parts.append(f"Genre: {row['playlist_genre']} / {sub}")
                else:
                    content_parts.append(f"Genre: {row['playlist_genre']}")
            if pd.notna(row.get("track_album_release_date")):
                content_parts.append(f"Release Date: {row['track_album_release_date']}")
            if pd.notna(row.get("track_popularity")) and row["track_popularity"] > 0:
                content_parts.append(f"Popularity: {row['track_popularity']}")
            if pd.notna(row.get("tempo")):
                content_parts.append(f"Tempo (BPM): {row['tempo']}")
            if pd.notna(row.get("energy")):
                content_parts.append(f"Energy: {row['energy']}")
            if pd.notna(row.get("danceability")):
                content_parts.append(f"Danceability: {row['danceability']}")
            if pd.notna(row.get("valence")):
                content_parts.append(f"Valence: {row['valence']}")

            page_content = "\n".join(content_parts).strip()
            if not page_content:
                continue

            metadata = {
                "source": self.path,
                "track_name": row.get("track_name", "") or "",
                "track_artist": row.get("track_artist", "") or "",
                "track_id": row.get("track_id", ""),
                "playlist_id": row.get("playlist_id", ""),
                "playlist_genre": row.get("playlist_genre", ""),
                "playlist_subgenre": row.get("playlist_subgenre", ""),
                "track_album_id": row.get("track_album_id", ""),
                "uri": row.get("uri", ""),
                "id": row.get("id", ""),
                "duration_ms": row.get("duration_ms", 0) or 0,
            }

            docs.append(Document(page_content=page_content, metadata=metadata))
        return docs


loader = DirectoryLoader(
    "Dataset/",
    glob="**/*.csv",
    loader_cls=CSVLoader,
)
