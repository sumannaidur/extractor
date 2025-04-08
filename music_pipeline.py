import os
import csv
import time
import librosa
import spotipy
import numpy as np
import pandas as pd
from ytmusicapi import YTMusic
from spotipy.oauth2 import SpotifyClientCredentials
from itertools import cycle
import subprocess

if os.path.exists("yt_cookies.txt"):
    print("🍪 Using yt_cookies.txt for yt-dlp.")
else:
    print("⚠️ yt_cookies.txt not found — yt-dlp might fail on Render.")


class MusicFeatureExtractor:
    def __init__(self, credentials_list, output_csv="song_features_combined.csv"):
        self.credentials_list = credentials_list
        self.cred_cycle = cycle(credentials_list)
        self.sp = self._get_valid_spotify_client()
        self.output_csv = output_csv
        self.ytmusic_client = YTMusic()  # ✅ avoid name conflict
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

    def _get_valid_spotify_client(self):
        while True:
            creds = next(self.cred_cycle)
            try:
                print(f"🔄 Trying Spotify client: {creds['client_id'][:5]}...")
                client = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
                    client_id=creds["client_id"],
                    client_secret=creds["client_secret"]
                ))
                client.search(q="test", type="track", limit=1)
                print("✅ Spotify client authenticated.")
                return client
            except Exception as e:
                print(f"❌ Failed to authenticate Spotify client: {e}")
                time.sleep(1)

    def _rotate_spotify_client(self):
        print("🔁 Rotating Spotify client...")
        self.sp = self._get_valid_spotify_client()

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
                self._rotate_spotify_client()
                time.sleep(2 ** attempt)
        return []

    def get_ytmusic_url(self, title, artist):
        try:
            query = f"{title} {artist}"
            print(f"🔍 YTMusic search query: {query}")
            results = self.ytmusic_client.search(query, filter="songs")  # ✅ correct object
            if results:
                for result in results:
                    if "videoId" in result:
                        return f"https://www.youtube.com/watch?v={result['videoId']}"
                print("⚠️ No videoId found in results.")
            else:
                print("⚠️ No results from YTMusic.")
        except Exception as e:
            print(f"❌ YTMusic error: {e}")
        return None

    def download_audio(self, youtube_url, out_path):
        try:
            print(f"🎧 Starting download: {youtube_url}")
            cmd = [
                "yt-dlp",
                "-f", "bestaudio[ext=m4a]",
                "--extract-audio",
                "--audio-format", "wav",
                "--output", out_path,
                "--cookies", "yt_cookies.txt",  # 👈 add this line
                youtube_url
            ]
            subprocess.run(cmd, check=True)
            if os.path.exists(out_path):
                print(f"✅ Downloaded and converted: {out_path}")
                return out_path
            else:
                print(f"❌ File not found after download: {out_path}")
                return None
        except subprocess.CalledProcessError as e:
            print(f"❌ yt-dlp failed: {e}")
            return None


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
            print(f"✅ Skipping (already processed): {song['Title']} by {song['Artist']} ({song['Spotify ID']})")
            return

        print(f"🎵 Processing: {song['Title']} by {song['Artist']}")
        url = self.get_ytmusic_url(song["Title"], song["Artist"])
        if not url:
            print(f"⚠️ No YTMusic URL found for {song['Title']} by {song['Artist']}")
            return

        lang = song["language"]
        year = song["year"]
        audio_path = self.get_audio_path(song["Spotify ID"], lang, year)
        audio_path = self.download_audio(url, audio_path)
        if not audio_path:
            print(f"⚠️ Audio download failed for: {song['Title']}")
            return

        features = self.extract_features(audio_path)

        if os.path.exists(audio_path):
            os.remove(audio_path)
            print(f"🗑️ Removed audio file: {audio_path}")

        if features:
            combined = {**song, **features}
            with open(self.output_csv, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.csv_columns)
                writer.writerow(combined)
                print(f"📁 Saved to main CSV: {self.output_csv}")

            out_dir = os.path.join("songs_by_year", lang)
            os.makedirs(out_dir, exist_ok=True)
            out_file = os.path.join(out_dir, f"{year}.csv")
            pd.DataFrame([combined]).to_csv(out_file, mode='a', header=not os.path.exists(out_file), index=False)
            print(f"📂 Saved to year-wise CSV: {out_file}")

            self.processed_ids.add(song["Spotify ID"])
