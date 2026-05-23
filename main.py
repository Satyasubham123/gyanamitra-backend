import os
import urllib.parse
import random
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from groq import Groq
from google import genai
import firebase_admin
from firebase_admin import credentials, firestore

load_dotenv()

# Initialize Firebase Admin for Caching (You will need to add your serviceAccountKey.json later)
# cred = credentials.Certificate("serviceAccountKey.json")
# firebase_admin.initialize_app(cred)
# db = firestore.client()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    prompt: str
    targetLanguage: str # 'English', 'Odia', 'Hindi'
    history: list

class ImageRequest(BaseModel):
    prompt: str
    subject: str

# --- AI ENGINES ---
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def translate_text(text: str, target_lang: str) -> str:
    if target_lang.lower() == 'english': return text
    
    # Use Groq (Llama 3) for blazing fast, free translation
    sys_prompt = f"You are a professional translator. Translate the following text into {target_lang}. Output ONLY the translated text, nothing else."
    res = groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": text}]
    )
    return res.choices[0].message.content

def process_educational_ai(english_prompt: str, history: list) -> str:
    system_instruction = "You are GyanMitra, an expert AI tutor for Indian school students. Explain concepts simply, accurately, and conversationally."
    
    # 🛡️ Try 1: Groq (Primary)
    try:
        messages = [{"role": "system", "content": system_instruction}, {"role": "user", "content": english_prompt}]
        res = groq_client.chat.completions.create(model="llama-3.3-70b-versatile", messages=messages)
        return res.choices[0].message.content
    except Exception as e:
        print(f"Groq failed: {e}")

    # 🛡️ Try 2: Gemini (Fallback)
    try:
        res = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=system_instruction + "\nUser: " + english_prompt
        )
        return res.text
    except Exception as e:
        print(f"Gemini failed: {e}")
        raise Exception("All AI providers failed.")


@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        # Step 1: Check Cache (Pseudocode for future Firestore implementation)
        # cache_ref = db.collection('ai_cache').document(hash(request.prompt))
        # if cache_ref.get().exists: return {"text": cache_ref.get().to_dict()['response']}

        # Step 2: Translate Input to English (if needed)
        english_prompt = request.prompt
        if request.targetLanguage != 'English':
            english_prompt = translate_text(request.prompt, 'English')

        # Step 3: Process with Educational AI Fallback System
        english_response = process_educational_ai(english_prompt, request.history)

        # Step 4: Translate Back to Student's Language
        final_response = english_response
        if request.targetLanguage != 'English':
            final_response = translate_text(english_response, request.targetLanguage)

        # Step 5: Save to Cache (Pseudocode)
        # cache_ref.set({"prompt": request.prompt, "response": final_response})

        return {"text": final_response}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/generate-image")
async def generate_image(request: ImageRequest):
    try:
        # 1. Supercharge the prompt for educational clarity
        # We force "vector graphic" and "readable text" to get clean lines instead of blurry paintings.
        full_prompt = f"High resolution crisp educational vector graphic diagram of {request.subject}, {request.prompt}. Clean white background, highly detailed, sharp lines. PERFECTLY READABLE ENGLISH TEXT, clear labels."
        
        safe_prompt = urllib.parse.quote(full_prompt)
        seed = random.randint(1, 1000000)
        
        # 2. Add '&model=flux' to the URL! This is the secret weapon for good text.
        image_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?seed={seed}&width=1024&height=1024&nologo=true&model=flux"
        
        return {"image_url": image_url}
    except Exception as e:
        print(f"Image generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def read_root():
    return {"status": "GyanMitra Backend is Running"}