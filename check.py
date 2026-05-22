import os
import google.generativeai as genai
from dotenv import load_dotenv

# Load your exact API key
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("Error: Could not find API key in .env")
else:
    genai.configure(api_key=api_key)
    print("🔑 Connecting to Google...")
    print("Here are the exact models your key is allowed to use:\n")
    
    # Ask Google for the official list
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(m.name)
            
    print("\n✅ Check complete!")