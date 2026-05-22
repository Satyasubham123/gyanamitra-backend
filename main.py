import os
import urllib.parse
import random
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import google.generativeai as genai

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
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY is missing from Render Environment!")

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=request.systemInstruction
        )
        print("🟡 2. Sending message to Gemini...")
        response = model.generate_content(request.formattedContents)
        print("🟢 3. SUCCESS: Gemini replied!")
        return {"text": response.text}
        
    except Exception as e:
        print(f"🔴 ERROR from Gemini: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# 🚀 NEW: Instant Image Generation via Pollinations (NO API KEY NEEDED)
@app.post("/api/generate-image")
async def generate_image(request: ImageRequest):
    print(f"🎨 Generating image for: {request.prompt}...")
    try:
        # 1. Safely format the prompt for a URL (e.g., changes spaces to %20)
        safe_prompt = urllib.parse.quote(request.prompt)
        
        # 2. Generate a random seed so the browser doesn't cache the same image
        seed = random.randint(1, 1000000)
        
        # 3. Build the Pollinations URL (High quality, 1024x1024, no watermark)
        image_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?seed={seed}&width=1024&height=1024&nologo=true"
        
        print("🟢 SUCCESS: Image generated instantly via Pollinations!")
        
        # 4. Return the URL directly to your React frontend!
        return {"image_url": image_url}
        
    except Exception as e:
        print(f"🔴 ERROR generating image: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.api_route("/", methods=["GET", "HEAD"])
def read_root():
    return {"status": "GyanMitra Server is running on the Ultimate Free Stack!"}