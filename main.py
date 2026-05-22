import os
import urllib.parse
import random
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from groq import Groq

# Load environment variables
load_dotenv()

app = FastAPI()

# ☢️ THE NUCLEAR CORS FIX ☢️
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

@app.post("/ask")
async def ask_gyanamitra(request: ChatRequest):
    print("\n🟢 1. SUCCESS: Frontend reached Python!")
    
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("🔴 ERROR: GROQ_API_KEY is missing from Render!")
        raise HTTPException(status_code=500, detail="GROQ_API_KEY is missing!")

    try:
        client = Groq(api_key=api_key)
        
        # 🚀 NEW: Properly format the chat history for Groq
        groq_messages = [{"role": "system", "content": request.systemInstruction}]
        
        for msg in request.formattedContents:
            # Change "model" to "assistant" (Groq uses 'assistant', Gemini used 'model')
            role = "assistant" if msg.get("role") == "model" else "user"
            
            # Safely extract the text from the parts array
            parts = msg.get("parts", [])
            text = parts[0].get("text", "") if parts else ""
            
            groq_messages.append({"role": role, "content": text})
            
        print("🟡 2. Sending formatted conversation to Groq...")
        chat_completion = client.chat.completions.create(
            messages=groq_messages,
            model="llama3-8b-8192", 
        )
        
        print("🟢 3. SUCCESS: Groq replied!")
        return {"text": chat_completion.choices[0].message.content}
        
    except Exception as e:
        print(f"🔴 ERROR from Groq: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# 🚀 Instant Image Generation via Pollinations
@app.post("/api/generate-image")
async def generate_image(request: ImageRequest):
    print(f"🎨 Generating image for: {request.prompt}...")
    try:
        safe_prompt = urllib.parse.quote(request.prompt)
        seed = random.randint(1, 1000000)
        
        image_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?seed={seed}&width=1024&height=1024&nologo=true"
        
        print("🟢 SUCCESS: Image generated instantly!")
        return {"image_url": image_url}
        
    except Exception as e:
        print(f"🔴 ERROR generating image: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.api_route("/", methods=["GET", "HEAD"])
def read_root():
    return {"status": "GyanMitra Server is running perfectly!"}