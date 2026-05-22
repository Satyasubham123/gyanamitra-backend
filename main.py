import os
import uuid
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import google.generativeai as genai
from huggingface_hub import InferenceClient

# Load the secret key
load_dotenv()

app = FastAPI()

# 🚀 UPDATED: Specific CORS policy to allow your Firebase app
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://gyanamitra-35109.firebaseapp.com",
        "http://localhost:5173", 
        "http://localhost:3000"
    ], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the Free Hugging Face AI
try:
    hf_client = InferenceClient(
        "runwayml/stable-diffusion-v1-5", 
        token=os.getenv("HUGGINGFACE_API_KEY")
    )
except Exception as e:
    print(f"Warning: Hugging Face client failed to initialize: {e}")


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
        print("🔴 ERROR: API Key missing!")
        raise HTTPException(status_code=500, detail="API Key missing")
        
    print("🟡 2. INFO: API Key found. Booting up Google SDK...")

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=request.systemInstruction
        )
        print("🟡 3. Sending your message to the AI...")
        response = model.generate_content(request.formattedContents)
        print("🟢 4. SUCCESS: The AI replied!")
        return {"text": response.text}
        
    except Exception as e:
        print(f"🔴 ERROR from Google SDK: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# 🚀 AI Image Generation Route (ImgBB Auto-Delete System)
@app.post("/api/generate-image")
async def generate_image(request: ImageRequest):
    print(f"🎨 Generating image for: {request.prompt}...")
    try:
        # 1. Ask Hugging Face to draw the image
        image = hf_client.text_to_image(request.prompt)
        
        # 2. Save it temporarily on the server
        temp_filename = f"temp_visual_{uuid.uuid4()}.png"
        image.save(temp_filename)
        
        # 3. Upload to ImgBB with the 3-day self-destruct timer
        print("☁️ Uploading to ImgBB (Auto-deletes in 3 days)...")
        imgbb_key = os.getenv("IMGBB_API_KEY")
        
        with open(temp_filename, "rb") as file:
            payload = {
                "key": imgbb_key,
                "expiration": 259200 
            }
            files = {
                "image": file
            }
            response = requests.post("https://api.imgbb.com/1/upload", data=payload, files=files)
            
        # 4. Get the URL from ImgBB's response
        if response.status_code == 200:
            image_url = response.json()["data"]["url"]
        else:
            print(f"ImgBB Error: {response.text}")
            raise Exception("Failed to upload image to cloud storage.")
            
        # 5. Clean up the temporary server file to save space
        os.remove(temp_filename)
        
        print("🟢 SUCCESS: Image generated and uploaded!")
        return {"image_url": image_url}
        
    except Exception as e:
        print(f"🔴 ERROR generating image: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def read_root():
    return {"status": "GyanMitra Backend is running securely!"}