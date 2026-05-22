import os
import urllib.parse
import random
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from groq import Groq
from google import genai # 🚀 UPDATED IMPORT

# Load environment variables (from Render dashboard)
load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    formattedContents: list
    systemInstruction: str

class ImageRequest(BaseModel):
    prompt: str
    subject: str

# --- THE ULTIMATE FALLBACK MANAGER ---
def generate_with_fallbacks(system_instruction: str, history: list) -> str:
    # 🛡️ Try 1: Groq (Primary Engine - Fastest)
    try:
        print("🟡 Trying Groq...")
        groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        groq_messages = [{"role": "system", "content": system_instruction}]
        
        for msg in history:
            role = "assistant" if msg.get("role") == "model" else "user"
            text = msg.get("parts", [{}])[0].get("text", "")
            groq_messages.append({"role": role, "content": text})
            
        res = groq_client.chat.completions.create(model="llama-3.1-8b-instant", messages=groq_messages)
        return res.choices[0].message.content
        
    except Exception as e:
        print(f"🔴 Groq Failed: {e}. Switching to Gemini...")

    # 🛡️ Try 2: Gemini (Fallback 1 - Best for Indic Languages)
    try:
        print("🟡 Trying Gemini...")
        # 🚀 UPDATED GEMINI CODE
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        
        # Convert Groq history format to Gemini format
        gemini_prompt = system_instruction + "\n\n"
        for msg in history:
            role = "AI" if msg.get("role") == "model" else "User"
            text = msg.get("parts", [{}])[0].get("text", "")
            gemini_prompt += f"{role}: {text}\n"
            
        res = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=gemini_prompt
        )
        return res.text
        
    except Exception as e:
        print(f"🔴 Gemini Failed: {e}. Switching to OpenRouter...")

    # 🛡️ Try 3: OpenRouter (Ultimate Fallback - Safety Net)
    try:
        print("🟡 Trying OpenRouter...")
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        or_messages = [{"role": "system", "content": system_instruction}]
        
        for msg in history:
            role = "assistant" if msg.get("role") == "model" else "user"
            text = msg.get("parts", [{}])[0].get("text", "")
            or_messages.append({"role": role, "content": text})
            
        headers = {
            "Authorization": f"Bearer {openrouter_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://gyanamitra.com",
            "X-Title": "GyanMitra"
        }
        payload = {"model": "google/gemma-2-9b-it:free", "messages": or_messages}
        req = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
        
        return req.json()["choices"][0]["message"]["content"]
        
    except Exception as e:
        print(f"🔴 OpenRouter Failed: {e}")
        raise HTTPException(status_code=500, detail="All AI providers failed. Please try again later.")


# --- API ENDPOINTS ---
@app.post("/ask")
async def ask_gyanamitra(request: ChatRequest):
    try:
        answer = generate_with_fallbacks(request.systemInstruction, request.formattedContents)
        return {"text": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/generate-image")
async def generate_image(request: ImageRequest):
    try:
        # Combine subject and prompt natively for Pollinations
        full_prompt = f"Highly detailed educational diagram of {request.subject}, {request.prompt}, clean white background, digital art"
        safe_prompt = urllib.parse.quote(full_prompt)
        seed = random.randint(1, 1000000)
        
        image_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?seed={seed}&width=1024&height=1024&nologo=true"
        return {"image_url": image_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.api_route("/", methods=["GET", "HEAD"])
def read_root():
    return {"status": "GyanMitra Multi-Provider Backend is LIVE!"}