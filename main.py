import os
import json
import json as pyjson
import urllib.parse
import random
import hashlib
import base64
import requests 
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta
import jwt
from passlib.context import CryptContext
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
from groq import Groq
from google import genai
from google.genai import types
import firebase_admin
from firebase_admin import credentials, firestore

load_dotenv()

origins = [
    "https://satyagyana.web.app",     # YOUR LIVE FRONTEND
    "https://satyagyana.firebaseapp.com",
    "http://localhost:5173", 
    "http://localhost:3000"           # Alternative Firebase link
]

# ==========================================
# 1. AUTHENTICATION & DATABASE SETUP
# ==========================================
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./users.db")
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_verified = Column(Boolean, default=False) 
    first_name = Column(String)
    middle_name = Column(String, nullable=True)
    last_name = Column(String)
    class_level = Column(String)
    state = Column(String)
    medium = Column(String)
    gender = Column(String)
    role = Column(String, default="student")
    subscription_plan = Column(String, default="trial")
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# Setup Password Hashing and JWT (Must be BEFORE ensure_superusers)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-super-secret-key-change-this-later") 
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def ensure_superusers():
    db = SessionLocal()
    try:
        # Securely hash your hardcoded password
        master_password = pwd_context.hash("Arpita@700")
        
        special_users = [
            {
                "email": "satyagyanaedu@gmail.com",
                "first_name": "System",
                "last_name": "Admin",
                "role": "admin",
                "subscription_plan": "lifetime"
            },
            {
                "email": "biswalsatya321@gmail.com",
                "first_name": "Satya",
                "last_name": "Biswal",
                "role": "student",
                "subscription_plan": "premium" # All-time premium
            }
        ]

        for su in special_users:
            existing_user = db.query(User).filter(User.email == su["email"]).first()
            
            if not existing_user:
                # If they don't exist, create them instantly!
                new_user = User(
                    email=su["email"],
                    hashed_password=master_password,
                    is_verified=True, # Bypass email verification
                    first_name=su["first_name"],
                    last_name=su["last_name"],
                    role=su["role"],
                    subscription_plan=su["subscription_plan"],
                    class_level="Master",
                    state="Odisha",
                    medium="English",
                    gender="Male"
                )
                db.add(new_user)
            else:
                # If they do exist, force upgrade them just in case!
                existing_user.role = su["role"]
                existing_user.subscription_plan = su["subscription_plan"]
                existing_user.is_verified = True # Ensure they are never locked out
                
        db.commit()
        print("✅ Superusers (Admin & Premium) successfully locked into the database.")
    except Exception as e:
        print(f"⚠️ Error ensuring superusers: {e}")
    finally:
        db.close()

# Run the function every time the server starts
ensure_superusers()


# ==========================================
# 2. EMAIL VERIFICATION HELPER
# ==========================================
def send_verification_email(user_email: str, token: str):
    # This is the link the user will click in their email
    # Update localhost to your real domain when you deploy!
    verify_link = f"http://localhost:5173/verify?token={token}"
    
    sender_email = os.getenv("EMAIL_ADDRESS")
    app_password = os.getenv("EMAIL_APP_PASSWORD")

    if not sender_email or not app_password:
        print("⚠️ Email credentials not found in .env! Cannot send verification email.")
        return

    msg = EmailMessage()
    msg['Subject'] = 'Welcome to GyanMitra! Please verify your email'
    msg['From'] = sender_email
    msg['To'] = user_email
    
    email_body = f"""Hello!

Welcome to the GyanMitra platform. We are thrilled to have you!

Please click the link below to verify your email address and activate your account:
{verify_link}

If you did not request this, please ignore this email.
"""
    msg.set_content(email_body)

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(sender_email, app_password)
            smtp.send_message(msg)
            print(f"✅ Verification email sent successfully to {user_email}")
    except Exception as e:
        print(f"⚠️ Failed to send verification email: {e}")


# ==========================================
# 3. FIREBASE & SUPABASE SETUP
# ==========================================
firebase_app = None
if not firebase_admin._apps:
    service_account_info = os.getenv("FIREBASE_SERVICE_ACCOUNT")
    if service_account_info:
        try:
            cred_dict = json.loads(service_account_info)
            cred = credentials.Certificate(cred_dict)
            firebase_app = firebase_admin.initialize_app(cred)
            db_firestore = firestore.client()
            print("✅ Firebase Admin Initialized Successfully")
        except Exception as e:
            print(f"⚠️ Error initializing Firebase Admin: {e}")
            db_firestore = None
    else:
        print("⚠️ WARNING: FIREBASE_SERVICE_ACCOUNT env var not found. Caching will be disabled.")
        db_firestore = None

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    SUPABASE_HEADERS = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    print("✅ Supabase REST API Configured")
else:
    SUPABASE_HEADERS = None
    print("⚠️ WARNING: Supabase keys not found.")


# ==========================================
# 4. FASTAPI APP & PYDANTIC MODELS
# ==========================================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins, 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class UserCreate(BaseModel):
    email: str
    password: str
    firstName: str
    middleName: Optional[str] = None
    lastName: str
    classLevel: str
    state: str
    medium: str
    gender: str
    role: str = "student"

class UserLogin(BaseModel):
    email: str
    password: str

class ChatRequest(BaseModel):
    prompt: str
    targetLanguage: str
    history: list

class ImageRequest(BaseModel):
    prompt: str
    subject: str

class AnalyzeRequest(BaseModel):
    image_base64: str
    prompt: str
    targetLanguage: str

class WordRequest(BaseModel):
    word: str
    targetLanguage: str = "Odia"


# ==========================================
# 5. AI ENGINES & HELPERS
# ==========================================
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def translate_text(text: str, target_lang: str) -> str:
    if target_lang.lower() == 'english': return text
    sys_prompt = f"You are a professional translator. Translate the following text into {target_lang}. Output ONLY the translated text, nothing else."
    res = groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": text}]
    )
    return res.choices[0].message.content

def process_educational_ai(english_prompt: str, history: list) -> str:
    system_instruction = """You are GyanMitra, an expert AI tutor for Indian school students. Explain concepts simply, accurately, and conversationally.
    IMPORTANT KNOWLEDGE: If a student asks about "Satya Subham Biswal", "Satya", or the founder/creator of this platform, you must proudly and respectfully state that Satya Subham Biswal is the visionary Founder, a great teacher, and the brilliant mind behind the GyanMitra platform. He created this platform to provide free, high-quality AI education to students in India."""
    
    try:
        messages = [{"role": "system", "content": system_instruction}, {"role": "user", "content": english_prompt}]
        res = groq_client.chat.completions.create(model="llama-3.3-70b-versatile", messages=messages)
        return res.choices[0].message.content
    except Exception as e:
        print(f"Groq failed: {e}")

    try:
        res = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=system_instruction + "\nUser: " + english_prompt
        )
        return res.text
    except Exception as e:
        print(f"Gemini failed: {e}")
        raise Exception("All AI providers failed.")

def generate_cache_key(text: str) -> str:
    return hashlib.md5(text.lower().strip().encode()).hexdigest()


# ==========================================
# 6. API ENDPOINTS (AUTH & AI)
# ==========================================

@app.post("/api/register")
async def register(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_pw = pwd_context.hash(user.password)
    
    new_user = User(
        email=user.email, 
        hashed_password=hashed_pw,
        first_name=user.firstName,
        middle_name=user.middleName,
        last_name=user.lastName,
        class_level=user.classLevel,
        state=user.state,
        medium=user.medium,
        gender=user.gender,
        role=user.role
    )
    
    db.add(new_user)
    db.commit()
    
    # Create a verification token (expires in 24 hours)
    expire = datetime.utcnow() + timedelta(hours=24)
    verify_token = jwt.encode({"sub": user.email, "type": "verify", "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)
    
    # Send the email via Gmail App Password
    send_verification_email(user.email, verify_token)
    
    return {"msg": "User registered successfully! Please check your email to verify your account."}

@app.get("/api/verify")
async def verify_email(token: str, db: Session = Depends(get_db)):
    try:
        # Decode the token to see who it belongs to
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        token_type = payload.get("type")
        
        if token_type != "verify":
            raise HTTPException(status_code=400, detail="Invalid token type")
            
        # Find the user and mark them as verified
        db_user = db.query(User).filter(User.email == email).first()
        if not db_user:
            raise HTTPException(status_code=404, detail="User not found")
            
        db_user.is_verified = True
        db.commit()
        
        return {"msg": "Email successfully verified! You can now log in."}
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="Verification link has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=400, detail="Invalid verification link")

@app.post("/api/login")
async def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.email).first()
    
    if not db_user or not pwd_context.verify(user.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
        
    # Check if they have verified their email
    if not db_user.is_verified:
         raise HTTPException(status_code=403, detail="Please verify your email before logging in.")
    
    # Generate login token valid for 7 days
    expire = datetime.utcnow() + timedelta(days=7)
    encoded_jwt = jwt.encode({"sub": user.email, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)
    
    return {"access_token": encoded_jwt, "token_type": "bearer"}

@app.post("/api/dictionary/search")
async def search_vocabulary(request: WordRequest):
    if not SUPABASE_HEADERS or not SUPABASE_URL:
        raise HTTPException(status_code=500, detail="Database not configured.")
        
    try:
        english_word = request.word.strip().lower()
        if request.targetLanguage != 'English':
            english_word = translate_text(request.word, 'English').strip().lower()

        cache_url = f"{SUPABASE_URL}/rest/v1/global_dictionary?word_english=eq.{urllib.parse.quote(english_word)}&select=*"
        res = requests.get(cache_url, headers=SUPABASE_HEADERS)
        
        if res.status_code == 200:
            cached_data = res.json()
            if len(cached_data) > 0:
                print(f"🚀 SUPABASE CACHE HIT for: {english_word}")
                return cached_data[0]

        print(f"🐢 CACHE MISS. Generating deep profile for: {english_word}")
        
        system_prompt = """You are an expert multilingual tutor and memory coach for Odisha students.
        Output ONLY valid JSON. Keep technical educational words transliterated in Odia and Hindi if that is how students naturally read them.
        
        You must return exactly this JSON structure:
        {
            "word_english": "The english word",
            "word_odia": "Odia translation",
            "word_hindi": "Hindi translation",
            "part_of_speech": "Noun/Verb/etc",
            "explanation": "Simple explanation suitable for a 10th-grade student.",
            "mnemonic": "A highly visual and memorable trick to remember the word (e.g. 'Imagine a balloon INFLATING').",
            "synonyms": ["syn1", "syn2"],
            "antonyms": ["ant1", "ant2"]
        }"""

        groq_res = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Generate profile for the word: {english_word}"}
            ],
            response_format={"type": "json_object"}
        )
        
        ai_data = pyjson.loads(groq_res.choices[0].message.content)
        ai_data["word_english"] = english_word

        image_prompt = f"High quality educational illustration representing the concept of {english_word}, textbook style, clean white background, highly detailed"
        safe_prompt = urllib.parse.quote(image_prompt)
        seed = random.randint(1, 1000000)
        ai_data['image_url'] = f"https://image.pollinations.ai/prompt/{safe_prompt}?seed={seed}&width=800&height=800&nologo=true&model=flux"

        insert_url = f"{SUPABASE_URL}/rest/v1/global_dictionary"
        requests.post(insert_url, headers=SUPABASE_HEADERS, json=ai_data)

        return ai_data

    except Exception as e:
        print(f"Dictionary API Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        english_prompt = request.prompt
        if request.targetLanguage != 'English':
            english_prompt = translate_text(request.prompt, 'English')

        cache_key = generate_cache_key(english_prompt)
        if db_firestore is not None:
            cache_ref = db_firestore.collection('ai_global_cache').document(cache_key)
            cached_doc = cache_ref.get()
            
            if cached_doc.exists:
                print(f"🚀 CACHE HIT! Returning saved answer for: {english_prompt}")
                english_response = cached_doc.to_dict().get('response')
                final_response = english_response
                if request.targetLanguage != 'English':
                    final_response = translate_text(english_response, request.targetLanguage)
                return {"text": final_response}

        print("🐢 CACHE MISS. Generating new answer from AI...")
        english_response = process_educational_ai(english_prompt, request.history)

        if db_firestore is not None:
            cache_ref.set({
                "prompt": english_prompt,
                "response": english_response,
                "timestamp": firestore.SERVER_TIMESTAMP
            })

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
        full_prompt = f"High resolution crisp educational vector graphic diagram of {request.subject}, {request.prompt}. Clean white background, highly detailed, sharp lines. PERFECTLY READABLE ENGLISH TEXT, clear labels."
        safe_prompt = urllib.parse.quote(full_prompt)
        seed = random.randint(1, 1000000)
        image_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?seed={seed}&width=1024&height=1024&nologo=true&model=flux"
        return {"image_url": image_url}
    except Exception as e:
        print(f"Image generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/analyze-image")
async def analyze_image_endpoint(request: AnalyzeRequest):
    try:
        encoded_data = request.image_base64
        mime_type = "image/jpeg"
        if "," in request.image_base64:
            header, encoded_data = request.image_base64.split(",", 1)
            mime_type = header.split(":")[1].split(";")[0]
            
        image_bytes = base64.b64decode(encoded_data)

        english_prompt = request.prompt
        if request.targetLanguage != 'English' and request.prompt.strip():
            english_prompt = translate_text(request.prompt, 'English')

        system_instruction = """You are GyanMitra, an expert AI tutor. Analyze the uploaded image carefully. 
        - If it's a diagram, explain its parts clearly. 
        - If it's a math/science problem, solve it step-by-step. 
        - If it's handwritten notes, transcribe and summarize them.
        IMPORTANT KNOWLEDGE: If asked about the creator, state that Satya Subham Biswal is the visionary Founder and great teacher who built the GyanMitra platform."""
        
        full_prompt = f"{system_instruction}\n\nStudent asks: {english_prompt if english_prompt else 'Please explain this image.'}"

        image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        res = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[full_prompt, image_part]
        )
        
        english_response = res.text

        final_response = english_response
        if request.targetLanguage != 'English':
            final_response = translate_text(english_response, request.targetLanguage)

        return {"text": final_response}

    except Exception as e:
        print(f"Vision API Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze image.")

# --- SECURE PROFILE DEPENDENCY ---
async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        # 1. Decode the token to get the email
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid authentication token")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    # 2. Find the user in the database
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    
    return user

# --- GET CURRENT USER PROFILE ENDPOINT ---
@app.get("/api/users/me")
async def read_users_me(current_user: User = Depends(get_current_user)):
    # 🚀 Calculate 30-day trial status
    is_trial_expired = False
    days_left_in_trial = 0
    
    if current_user.subscription_plan == "trial":
        # Check how much time has passed since they registered
        trial_end_date = current_user.created_at + timedelta(days=30)
        time_left = trial_end_date - datetime.utcnow()
        
        if time_left.total_seconds() < 0:
            is_trial_expired = True
        else:
            days_left_in_trial = time_left.days
            
    # This automatically runs the token check above!
    # If the token is valid, it returns the user's full database row.
    return {
        "email": current_user.email,
        "firstName": current_user.first_name,
        "middleName": current_user.middle_name,
        "lastName": current_user.last_name,
        "classLevel": current_user.class_level,
        "state": current_user.state,
        "medium": current_user.medium,
        "gender": current_user.gender,
        "role": current_user.role,
        "is_verified": current_user.is_verified,
        "subscriptionPlan": current_user.subscription_plan,
        "isTrialExpired": is_trial_expired,
        "daysLeftInTrial": days_left_in_trial,
        # Create a nice display name combining first and last name
        "displayName": f"{current_user.first_name} {current_user.last_name}".strip()
    }

# --- ADMIN SECURITY LOCK ---
async def get_admin_user(current_user: User = Depends(get_current_user)):
    # Block anyone who isn't an admin!
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied. Authorized Admin Personnel only.")
    return current_user

# --- GET ALL STUDENTS (ADMIN ONLY) ---
@app.get("/api/admin/users")
async def get_all_users(admin: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    # This queries the SQLite database for every single user row
    users = db.query(User).all()
    
    # Format the data neatly to send to React
    student_list = []
    for u in users:
        student_list.append({
            "id": u.id,
            "email": u.email,
            "firstName": u.first_name,
            "lastName": u.last_name,
            "classLevel": u.class_level,
            "state": u.state,
            "role": u.role,
            "is_verified": u.is_verified
        })
        
    return student_list

@app.get("/")
def read_root():
    return {"status": "GyanMitra Backend is Running with Email Auth and User Profiles!"}