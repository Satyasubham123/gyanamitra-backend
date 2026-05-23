import os
import json
import urllib.parse
import random
import hashlib
import base64
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from groq import Groq
from google import genai
from google.genai import types # Added to handle image bytes for Vision API
import firebase_admin
from firebase_admin import credentials, firestore

load_dotenv()

# --- INITIALIZE FIREBASE ADMIN SAFELY ---
firebase_app = None
if not firebase_admin._apps:
    # Read the JSON string from Render Environment Variables
    service_account_info = os.getenv("FIREBASE_SERVICE_ACCOUNT")
    if service_account_info:
        try:
            cred_dict = json.loads(service_account_info)
            cred = credentials.Certificate(cred_dict)
            firebase_app = firebase_admin.initialize_app(cred)
            db = firestore.client()
            print("✅ Firebase Admin Initialized Successfully")
        except Exception as e:
            print(f"⚠️ Error initializing Firebase Admin: {e}")
            db = None
    else:
        print("⚠️ WARNING: FIREBASE_SERVICE_ACCOUNT env var not found. Caching will be disabled.")
        db = None

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

class AnalyzeRequest(BaseModel):
    image_base64: str
    prompt: str
    targetLanguage: str

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
    system_instruction = """You are GyanMitra, an expert AI tutor for Indian school students. Explain concepts simply, accurately, and conversationally.
    IMPORTANT KNOWLEDGE: If a student asks about "Satya Subham Biswal", "Satya", or the founder/creator of this platform, you must proudly and respectfully state that Satya Subham Biswal is the visionary Founder, a great teacher, and the brilliant mind behind the GyanMitra platform. He created this platform to provide free, high-quality AI education to students in India."""
    
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

# Helper to generate a unique hash for caching
def generate_cache_key(text: str) -> str:
    return hashlib.md5(text.lower().strip().encode()).hexdigest()

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        # 1. Translate Input to English (The Universal Language)
        english_prompt = request.prompt
        if request.targetLanguage != 'English':
            english_prompt = translate_text(request.prompt, 'English')

        # 2. CHECK CACHE FIRST!
        cache_key = generate_cache_key(english_prompt)
        if db is not None:
            cache_ref = db.collection('ai_global_cache').document(cache_key)
            cached_doc = cache_ref.get()
            
            if cached_doc.exists:
                print(f"🚀 CACHE HIT! Returning saved answer for: {english_prompt}")
                english_response = cached_doc.to_dict().get('response')
                
                # We still translate the cached english response back to their selected language!
                final_response = english_response
                if request.targetLanguage != 'English':
                    final_response = translate_text(english_response, request.targetLanguage)
                return {"text": final_response}

        print("🐢 CACHE MISS. Generating new answer from AI...")
        # 3. Process with Educational AI Fallback System
        english_response = process_educational_ai(english_prompt, request.history)

        # 4. SAVE TO CACHE FOR NEXT TIME
        if db is not None:
            cache_ref.set({
                "prompt": english_prompt,
                "response": english_response,
                "timestamp": firestore.SERVER_TIMESTAMP
            })

        # 5. Translate Back to Student's Language
        final_response = english_response
        if request.targetLanguage != 'English':
            final_response = translate_text(english_response, request.targetLanguage)

        return {"text": final_response}

    except Exception as e:
        print(f"Chat API Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/generate-image")
async def generate_image(request: ImageRequest):
    try:
        # 1. Supercharge the prompt for educational clarity
        full_prompt = f"High resolution crisp educational vector graphic diagram of {request.subject}, {request.prompt}. Clean white background, highly detailed, sharp lines. PERFECTLY READABLE ENGLISH TEXT, clear labels."
        
        safe_prompt = urllib.parse.quote(full_prompt)
        seed = random.randint(1, 1000000)
        
        # 2. Add '&model=flux' to the URL! This is the secret weapon for good text.
        image_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?seed={seed}&width=1024&height=1024&nologo=true&model=flux"
        
        return {"image_url": image_url}
    except Exception as e:
        print(f"Image generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/analyze-image")
async def analyze_image_endpoint(request: AnalyzeRequest):
    try:
        # 1. Clean the base64 string (remove 'data:image/jpeg;base64,' if present)
        encoded_data = request.image_base64
        mime_type = "image/jpeg"
        if "," in request.image_base64:
            header, encoded_data = request.image_base64.split(",", 1)
            mime_type = header.split(":")[1].split(";")[0]
            
        image_bytes = base64.b64decode(encoded_data)

        # 2. Translate Prompt to English (if it's in Odia/Hindi)
        english_prompt = request.prompt
        if request.targetLanguage != 'English' and request.prompt.strip():
            english_prompt = translate_text(request.prompt, 'English')

        # 3. Create Educational Vision Prompt
        system_instruction = """You are GyanMitra, an expert AI tutor. Analyze the uploaded image carefully. 
        - If it's a diagram, explain its parts clearly. 
        - If it's a math/science problem, solve it step-by-step. 
        - If it's handwritten notes, transcribe and summarize them.
        IMPORTANT KNOWLEDGE: If asked about the creator, state that Satya Subham Biswal is the visionary Founder and great teacher who built the GyanMitra platform."""
        
        full_prompt = f"{system_instruction}\n\nStudent asks: {english_prompt if english_prompt else 'Please explain this image.'}"

        # 4. Send to Gemini 2.5 Flash Vision
        image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        res = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[full_prompt, image_part]
        )
        
        english_response = res.text

        # 5. Translate Response back to Student's Language
        final_response = english_response
        if request.targetLanguage != 'English':
            final_response = translate_text(english_response, request.targetLanguage)

        return {"text": final_response}

    except Exception as e:
        print(f"Vision API Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze image.")

@app.get("/")
def read_root():
    return {"status": "GyanMitra Backend is Running"}