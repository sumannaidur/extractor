import os
import pandas as pd
from flask import Flask, render_template, request
from music_pipeline import MusicFeatureExtractor

app = Flask(__name__)

SPOTIFY_CREDENTIALS = [
    {"client_id": "15adf67aec934fe792bee0d467742326", "client_secret": "d03b2411aad24b8e80f3257660f9f10f"},
    {"client_id": "241765db513d43218e1e996b7d13d73f", "client_secret": "0fb1d0f0eed44f2e98d0e022335dd9e1"},
    {"client_id": "56bfb61f27234852826fd13e813174e6", "client_secret": "401f40941cba4f5bb2a0274f9fb34df2"}
]

extractor = MusicFeatureExtractor(SPOTIFY_CREDENTIALS)
movie_files = {
    "telugu": "movies_by_language/telugu_movies.csv",
    "kannada": "movies_by_language/kannada_movies.csv",
    "tamil": "movies_by_language/tamil_movies.csv",
    "hindi": "movies_by_language/hindi_movies.csv"
}

def run_music_pipeline():
    status = {}
    for lang, path in movie_files.items():
        status[lang] = {"processed": 0, "skipped": 0, "errors": 0}

        if not os.path.exists(path):
            print(f"⚠️ File not found: {path}")
            continue

        df = pd.read_csv(path)
        if not {'Title', 'Release Date', 'Language'}.issubset(df.columns):
            print(f"⚠️ Invalid format in: {path}")
            continue

        for _, row in df.iterrows():
            title = row.get("Title")
            release = row.get("Release Date")

            try:
                year = pd.to_datetime(release, errors="coerce", dayfirst=True).year
                if pd.isna(year) or year < 1900:
                    continue
            except:
                status[lang]["errors"] += 1
                continue

            try:
                tracks = extractor.fetch_album_tracks(title, lang, year)
                for track in tracks:
                    if track["Spotify ID"] in extractor.processed_ids:
                        status[lang]["skipped"] += 1
                        continue
                    extractor.process_song(track)
                    status[lang]["processed"] += 1
            except:
                status[lang]["errors"] += 1

    return status

@app.route('/')
def dashboard():
    stats = {}
    for lang in movie_files.keys():
        stats[lang] = {"total": 0}
        folder = f"songs_by_year/{lang}"
        if os.path.exists(folder):
            for f in os.listdir(folder):
                path = os.path.join(folder, f)
                if f.endswith(".csv"):
                    try:
                        df = pd.read_csv(path)
                        stats[lang]["total"] += len(df)
                    except:
                        pass
    return render_template("dashboard.html", stats=stats)

@app.route('/run', methods=["POST"])
def run():
    status = run_music_pipeline()
    return render_template("dashboard.html", status=status)

if __name__ == '__main__':
    app.run(debug=True)
