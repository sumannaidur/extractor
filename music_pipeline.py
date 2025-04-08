# music_pipeline.py

import os
import csv
import time
import librosa
import spotipy
import yt_dlp
import numpy as np
import pandas as pd
from datetime import datetime
from spotipy.oauth2 import SpotifyClientCredentials
from youtubesearchpython import VideosSearch

class MusicFeatureExtractor:
    def __init__(self, credentials_list, output_csv="song_features_combined.csv"):
        self.credentials_list = credentials_list
        self.current_client_index = 0
        self.sp = self._get_spotify_client()
        self.output_csv = output_csv
        self.csv_columns = [
            "Spotify ID", "Title", "Artist", "Album", "Release Date", "Popularity",
            "tempo", "loudness", "key", "danceability", "energy", "speechiness", "instrumentalness",
            "movie_title", "language", "year"
        ]
        self._setup_files()
        self.processed_ids = self._load_processed_ids()

    def _setup_files(self):
        os.makedirs("csvs", exist_ok=True)
        os.makedirs("audio_files", exist_ok=True)
        os.makedirs("songs_by_year", exist_ok=True)
        if not os.path.exists(self.output_csv):
            with open(self.output_csv, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(self.csv_columns)

    def _load_processed_ids(self):
        if os.path.exists(self.output_csv):
            df = pd.read_csv(self.output_csv)
            return set(df["Spotify ID"].dropna())
        return set()

    def _get_spotify_client(self):
        creds = self.credentials_list[self.current_client_index % len(self.credentials_list)]
        print(f"🔄 Using Spotify client #{self.current_client_index}")
        return spotipy.Spotify(auth_manager=SpotifyClientCredentials(
            client_id=creds["client_id"],
            client_secret=creds["client_secret"]
        ))

    def _rotate_spotify_client(self):
        self.current_client_index += 1
        self.sp = self._get_spotify_client()

    def get_audio_path(self, filename, lang, year):
        path = os.path.join("audio_files", lang, str(year))
        os.makedirs(path, exist_ok=True)
        return os.path.join(path, f"{filename}.wav")

    def fetch_album_tracks(self, title, lang, year, retries=3):
        query = f"{title} {lang} {year}"
        for attempt in range(retries):
            try:
                result = self.sp.search(q=query, type='album', limit=1)
                if result['albums']['items']:
                    album = result['albums']['items'][0]
                    album_id = album['id']
                    tracks = self.sp.album_tracks(album_id)['items']
                    return [{
                        "Spotify ID": t['id'],
                        "Title": t['name'],
                        "Artist": ", ".join(a['name'] for a in t['artists']),
                        "Album": album['name'],
                        "Release Date": album['release_date'],
                        "Popularity": 0,
                        "movie_title": title,
                        "language": lang,
                        "year": year
                    } for t in tracks]
            except Exception as e:
                print(f"❌ Spotify error: {e}")
                time.sleep(2 ** attempt)
                self._rotate_spotify_client()
        return []

    def get_youtube_url(self, title, artist):
        queries = [
            f"{title} {artist} YouTube Music",
            f"{title} {artist} official audio",
            f"{title} {artist} official song",
            f"{title} {artist} lyrics"
        ]
        for query in queries:
            try:
                result = VideosSearch(query, limit=3).result()
                for video in result.get("result", []):
                    video_title = video["title"].lower()
                    if all(term in video_title for term in [title.lower(), artist.lower()]):
                        return video["link"]
                if result["result"]:
                    return result["result"][0]["link"]
            except Exception as e:
                print(f"❌ YouTube search failed for query '{query}': {e}")
        return None

    def download_audio(self, youtube_url, out_path):
        ydl_opts = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": out_path.replace(".wav", ".%(ext)s"),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "192"
            }],
            "quiet": True,
            "noplaylist": True,
            "geo_bypass": True
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([youtube_url])
        except Exception as e:
            print(f"❌ yt-dlp download error: {e}")
            return None
        return out_path

    def extract_features(self, file_path):
        try:
            y, sr = librosa.load(file_path, sr=22050)
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            rms = np.mean(librosa.feature.rms(y=y))
            chroma = np.mean(librosa.feature.chroma_stft(y=y, sr=sr))
            contrast = np.mean(librosa.feature.spectral_contrast(y=y, sr=sr))
            mfcc = librosa.feature.mfcc(y=y, sr=sr)
            mfcc_mean = np.mean(mfcc, axis=1)
            zcr = np.mean(librosa.feature.zero_crossing_rate(y=y))

            return {
                "tempo": tempo,
                "loudness": rms,
                "key": chroma,
                "danceability": contrast,
                "energy": mfcc_mean[0] if len(mfcc_mean) > 0 else 0,
                "speechiness": mfcc_mean[1] if len(mfcc_mean) > 1 else 0,
                "instrumentalness": zcr
            }
        except Exception as e:
            print(f"❌ Feature extraction failed: {e}")
            return None

    def process_song(self, song):
        if song["Spotify ID"] in self.processed_ids:
            print(f"✅ Skipping: {song['Title']}")
            return

        print(f"🎵 Processing: {song['Title']} by {song['Artist']}")
        url = self.get_youtube_url(song["Title"], song["Artist"])
        if not url:
            return

        lang = song["language"]
        year = song["year"]
        audio_path = self.get_audio_path(song["Spotify ID"], lang, year)
        audio_path = self.download_audio(url, audio_path)
        if not audio_path:
            return

        features = self.extract_features(audio_path)

        if os.path.exists(audio_path):
            os.remove(audio_path)

        if features:
            combined = {**song, **features}
            with open(self.output_csv, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.csv_columns)
                writer.writerow(combined)

            out_dir = os.path.join("songs_by_year", lang)
            os.makedirs(out_dir, exist_ok=True)
            out_file = os.path.join(out_dir, f"{year}.csv")
            pd.DataFrame([combined]).to_csv(out_file, mode='a', header=not os.path.exists(out_file), index=False)

            self.processed_ids.add(song["Spotify ID"])
