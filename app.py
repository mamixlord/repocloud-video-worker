import os, subprocess, tempfile, requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

app = FastAPI()

WORKER_SECRET = os.getenv("WORKER_SECRET")
YT_CLIENT_ID = os.getenv("YT_CLIENT_ID")
YT_CLIENT_SECRET = os.getenv("YT_CLIENT_SECRET")
YT_REFRESH_TOKEN = os.getenv("YT_REFRESH_TOKEN")

class Payload(BaseModel):
    secret: str
    narration_text: str
    video_url: str
    music_url: str
    title: str
    hashtags: list

def download(url, path):
    r = requests.get(url)
    with open(path, "wb") as f:
        f.write(r.content)

def tts(text, out):
    r = requests.get(
        "https://api.streamelements.com/kappa/v2/speech",
        params={"voice": "en-US-Wavenet-C", "text": text}
    )
    with open(out, "wb") as f:
        f.write(r.content)

def ffmpeg(video, voice, music, out):
    subprocess.check_call([
        "ffmpeg","-y",
        "-i", video,
        "-i", voice,
        "-i", music,
        "-filter_complex",
        "[2:a]volume=0.2[a2];[1:a][a2]amix=inputs=2:duration=shortest[a]",
        "-map","0:v","-map","[a]",
        "-shortest",
        out
    ])

def upload_youtube(path, title, desc):
    creds = Credentials(
        None,
        refresh_token=YT_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=YT_CLIENT_ID,
        client_secret=YT_CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/youtube.upload"]
    )
    yt = build("youtube","v3",credentials=creds)
    req = yt.videos().insert(
        part="snippet,status",
        body={
            "snippet":{"title":title,"description":desc,"categoryId":"15"},
            "status":{"privacyStatus":"public"}
        },
        media_body=MediaFileUpload(path)
    )
    res = req.execute()
    return "https://youtu.be/" + res["id"]

@app.post("/upload")
def upload(p: Payload):
    if p.secret != WORKER_SECRET:
        raise HTTPException(401)

    with tempfile.TemporaryDirectory() as d:
        v = f"{d}/v.mp4"
        m = f"{d}/m.mp3"
        s = f"{d}/s.mp3"
        o = f"{d}/o.mp4"

        download(p.video_url, v)
        download(p.music_url, m)
        tts(p.narration_text, s)
        ffmpeg(v, s, m, o)

        link = upload_youtube(o, p.title, p.narration_text)
        return {"ok":True,"youtube_url":link}
