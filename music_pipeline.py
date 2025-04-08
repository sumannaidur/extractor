import os
import csv
import time
import librosa
import spotipy
import numpy as np
import pandas as pd
from pytube import YouTube
from ytmusicapi import YTMusic
from spotipy.oauth2 import SpotifyClientCredentials
from itertools import cycle

ytmusic = YTMusic()

class MusicFeatureExtractor:
    def __init__(self, credentials_list, output_csv="song_features_combined.csv"):
        self.credentials_list = credentials_list
        self.cred_cycle = cycle(credentials_list)
        self.sp = self._get_valid_spotify_client()
        self.output_csv = output_csv
        self.ytmusic = YTMusic()
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
                # Test credentials
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
                    return [ {
                        "Spotify ID": t['id'],
                        "Title": t['name'],
                        "Artist": ", ".join(a['name'] for a in t['artists']),
                        "Album": album['name'],
                        "Release Date": album['release_date'],
                        "Popularity": 0,
                        "movie_title": title,
                        "language": lang,
                        "year": year
                    } for t in tracks ]
            except Exception as e:
                print(f"❌ Spotify error: {e}")
                self._rotate_spotify_client()
                time.sleep(2 ** attempt)
        return []

    def get_ytmusic_url(self, title, artist):
        try:
            query = f"{title} {artist}"
            results = ytmusic.search(query, filter="songs")
            if results:
                video_id = results[0].get("videoId")
                return f"https://www.youtube.com/watch?v={video_id}" if video_id else None
        except Exception as e:
            print(f"❌ YTMusic error: {e}")
        return None

    def download_audio(self, youtube_url, out_path):
        try:
            yt = YouTube(youtube_url)
            stream = yt.streams.filter(only_audio=True, file_extension='mp4').first()
            temp_path = out_path.replace(".wav", ".mp4")
            stream.download(output_path=os.path.dirname(temp_path), filename=os.path.basename(temp_path))

            # Convert to WAV
            y, sr = librosa.load(temp_path, sr=22050)
            librosa.output.write_wav(out_path, y, sr)
            os.remove(temp_path)
            return out_path
        except Exception as e:
            print(f"❌ YouTube download error: {e}")
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
            print(f"✅ Skipping: {song['Title']}")
            return

        print(f"🎵 Processing: {song['Title']} by {song['Artist']}")
        url = self.get_ytmusic_url(song["Title"], song["Artist"])
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
