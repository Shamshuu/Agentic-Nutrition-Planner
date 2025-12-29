import streamlit as st
import os
import sqlite3
import hashlib
import re
import datetime
from streamlit_cookies_manager import EncryptedCookieManager
from google import genai
from groq import Groq
from dotenv import load_dotenv
from PIL import Image

# --- 1. INITIALIZATION ---
load_dotenv()
MAX_RETRIES = 5          # max correction attempts
CAL_TOLERANCE = 25 
st.set_page_config(page_title="Agentic Nutrition Planner", page_icon="🥗", layout="wide")

cookies = EncryptedCookieManager(
    prefix="nutrition_app",
    password=os.getenv("COOKIE_SECRET", "dev-secret-key")
)

if not cookies.ready():
    st.stop()
    
@st.cache_resource
def get_groq_client():
    return Groq(api_key=os.getenv("GROQ_API_KEY"))


groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
genai_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# --- 2. DATABASE & AUTH SYSTEM ---
def init_db():
    with sqlite3.connect('nutrition_memory.db') as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                username TEXT,
                password TEXT,
                age INTEGER,
                gender TEXT,
                height REAL,
                weight REAL,
                goal_weight REAL,
                activity TEXT,
                meals_per_day INTEGER,
                diet_type TEXT,
                sleep REAL,
                allergies TEXT,
                cuisine TEXT
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS diet_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT,
                plan_text TEXT,
                status TEXT, -- 'approved', 'rejected'
                feedback TEXT,
                created_at TIMESTAMP
            )
        ''')
        conn.commit()

def make_hashes(password): return hashlib.sha256(str.encode(password)).hexdigest()
def check_hashes(password, hashed_text): return make_hashes(password) == hashed_text
def is_valid_email(email): return re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", email) is not None

def add_user(email, username, password, age, gender, height, weight, goal_w, activity, meals, diet, sleep, allergies, cuisine):
    try:
        with sqlite3.connect('nutrition_memory.db') as conn:
            c = conn.cursor()
            c.execute('INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', 
                      (email, username, make_hashes(password), age, gender, height, weight, goal_w, activity, meals, diet, sleep, allergies, cuisine))
            conn.commit()
            return True
    except sqlite3.IntegrityError:
        return False

def login_user(email, password):
    with sqlite3.connect('nutrition_memory.db') as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE email = ?', (email,))
        data = c.fetchall()
        if data and check_hashes(password, data[0][2]):
            return data[0]
        return False

def get_user_by_email(email):
    with sqlite3.connect('nutrition_memory.db') as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE email = ?', (email,))
        data = c.fetchall()
        return data[0] if data else None

def save_diet_plan(email, plan_text, status, feedback=None):
    with sqlite3.connect('nutrition_memory.db') as conn:
        c = conn.cursor()
        c.execute('INSERT INTO diet_plans (email, plan_text, status, feedback, created_at) VALUES (?, ?, ?, ?, ?)',
            (email, plan_text, status, feedback, datetime.datetime.now()))
        conn.commit()
    
def get_approved_plans(email):
    with sqlite3.connect('nutrition_memory.db') as conn:
        c = conn.cursor()
        c.execute('SELECT created_at, plan_text FROM diet_plans WHERE email = ? AND status = "approved" ORDER BY created_at DESC', (email,))
        data = c.fetchall()
        return data

@st.cache_data(ttl=600)
def get_latest_approved_context(email):
    # """Fetches the most recent approved plan to give context to the Chat Agent"""
    plans = get_approved_plans(email)
    if plans:
        return plans[0][1] # Return the text of the latest plan
    return "No previous approved plans."

def update_user_profile(email, age, gender, height, weight, goal_w, activity, meals, diet, sleep, allergies, cuisine):
    with sqlite3.connect('nutrition_memory.db') as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE users SET 
            age=?, gender=?, height=?, weight=?, goal_weight=?, activity=?, meals_per_day=?, diet_type=?, sleep=?, allergies=?, cuisine=?
            WHERE email=?
        ''', (age, gender, height, weight, goal_w, activity, meals, diet, sleep, allergies, cuisine, email))
        conn.commit()
        
def logout():
    cookies.pop("user_email", None)
    cookies.save()
    st.session_state.clear()
    st.session_state["force_logged_out"] = True
    st.rerun()


def delete_user_account(email):
    with sqlite3.connect('nutrition_memory.db') as conn:
        c = conn.cursor()
        c.execute('DELETE FROM diet_plans WHERE email = ?', (email,))
        c.execute('DELETE FROM users WHERE email = ?', (email,))
        conn.commit()
    
    
@st.cache_resource
def get_db():
    return sqlite3.connect("nutrition_memory.db", check_same_thread=False)


init_db()

def calculate_needs(weight, height, age, gender, activity):
    if gender == "Male": bmr = (10 * weight) + (6.25 * height) - (5 * age) + 5
    else: bmr = (10 * weight) + (6.25 * height) - (5 * age) - 161
    multipliers = {"Sedentary": 1.2, "Active": 1.55, "Very Active": 1.9}
    return int(bmr * multipliers.get(activity, 1.2))

def calculate_protein(weight): return weight*2

CAL_DB = {
    "roti": 110,
    "chapati": 110,
    "rice_100g": 130,
    "egg": 70,
    "milk_250ml": 150,
    "banana": 105,
    "curd_200g": 120,
    "peanuts_30g": 170,
    "dal_100g": 120,
    "oats_50g": 190
}

# def enforce_minimum_calories(plan_text, target_cals, target_protein):
#     """
#     Lightweight calorie correction.
#     Adds safe calorie boosters if plan is under target.
#     """
#     match = re.search(r"Total:\s*(\d+)\s*kcal", plan_text)
#     if match:
#         estimated = int(match.group(1))
#     else:
#         # Fallback if total is missing
#         estimated = target_cals
        
#     protein_match = re.search(r"Total:\s*\d+\s*kcal,\s*(\d+)\s*gm protein", plan_text, re.IGNORECASE)

#     if protein_match:
#         total_protein = int(protein_match.group(1))
#     else:
#         total_protein = target_protein

#     if estimated >= target_cals:
#         return plan_text  # already acceptable

#     deficit = target_cals - estimated

#     boosters = []

#     if deficit > 0:
#         boosters.append("• 1 Banana (105 kcal)")
#         deficit -= 105

#     if deficit > 0:
#         boosters.append("• 250 ml Milk (150 kcal)")
#         deficit -= 150
        
        
#     protein_deficit = target_protein - total_protein

#     protein_boosters = []
    
#     if protein_deficit > 0:
#         protein_boosters.append("• 2 Boiled Eggs (+12 gm protein)")
#         protein_deficit -= 12

#     if protein_deficit > 0:
#         protein_boosters.append("• 200 g Curd (+10 gm protein)")
#         protein_deficit -= 10

#     if protein_deficit > 0:
#         protein_boosters.append("• 150 g Chicken Breast (+30 gm protein)")

#         correction = "\n\n⚡ **Calorie Adjustment Added Automatically**\n"
#         correction += "To meet daily energy needs, add:\n"
#         correction += "\n".join(boosters)

#     final_text= plan_text + correction
    
#     return final_text


# --- 3. MULTI-AGENT ENGINE ---

def run_agent(agent_role, agent_persona, user_context):
    # """Generic function to call a specific agent"""
    response = get_groq_client().chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": f"You are the {agent_role}. {agent_persona}"},
            {"role": "user", "content": user_context}
        ],
        temperature=0.3
    )
    return response.choices[0].message.content

def extract_calories(plan_text: str) -> int:
    """
    Extract total daily calories from a natural-language meal plan.
    Priority:
    1. Explicit daily total (e.g. 'Total: 2800 kcal')
    2. '#Total:' section
    3. Sum of meal calories (Breakfast/Lunch/Dinner/Snacks)
    """

    if not plan_text or not isinstance(plan_text, str):
        return 0

    text = plan_text.lower()

    # --------------------------------------------------
    # 1️⃣ STRONG SIGNAL: Explicit daily total
    # --------------------------------------------------
    explicit_patterns = [
        r"total\s*[:\-]?\s*(\d{3,5})\s*kcal",
        r"#\s*total\s*[:\-]?\s*(\d{3,5})",
        r"total calories\s*[:\-]?\s*(\d{3,5})",
    ]

    for pattern in explicit_patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                pass

    # --------------------------------------------------
    # 2️⃣ MEDIUM SIGNAL: Meal-wise calories
    # --------------------------------------------------
    meal_patterns = [
        r"breakfast\s*[:\-]?\s*(\d{2,4})\s*kcal",
        r"lunch\s*[:\-]?\s*(\d{2,4})\s*kcal",
        r"dinner\s*[:\-]?\s*(\d{2,4})\s*kcal",
        r"snacks?\s*[:\-]?\s*(\d{2,4})\s*kcal",
    ]

    total = 0
    found_any = False

    for pattern in meal_patterns:
        for match in re.findall(pattern, text):
            try:
                total += int(match)
                found_any = True
            except ValueError:
                continue

    if found_any:
        return total

    # --------------------------------------------------
    # 3️⃣ WEAK FALLBACK: Any kcal mentions (guarded)
    # --------------------------------------------------
    all_kcals = re.findall(r"(\d{2,4})\s*kcal", text)
    numeric_kcals = [int(x) for x in all_kcals if 50 <= int(x) <= 2000]

    if numeric_kcals:
        # Avoid double counting: sum only if reasonable
        summed = sum(numeric_kcals)
        if summed <= 6000:   # sanity cap
            return summed

    # --------------------------------------------------
    # 4️⃣ LAST RESORT
    # --------------------------------------------------
    return 0

def detect_user_intent(user_message, chat_history, has_pending_plan):
    """
    AI-Powered Intent Detection Agent
    Analyzes user message and determines the intent dynamically.
    Returns structured intent information.
    """
    # Build context about current state
    state_context = ""
    if has_pending_plan:
        state_context = "There is currently a PROPOSED diet plan displayed on screen (not yet approved)."
    else:
        state_context = "There is NO pending plan on screen currently."
    
    # Check if last message was asking for duration
    last_was_duration_question = False
    if len(chat_history) >= 2:
        last_assistant_msg = chat_history[-2].get("content", "") if chat_history[-2].get("role") == "assistant" else ""
        if "how many days" in last_assistant_msg.lower():
            last_was_duration_question = True
    
    intent_prompt = f"""
    You are an Intent Detection Agent for a Nutrition Planning System.

    CURRENT STATE:
    {state_context}
    Last assistant message was asking for duration: {last_was_duration_question}

    USER MESSAGE: "{user_message}"

    CHAT HISTORY (last 3 messages):
    {str(chat_history[-3:]) if len(chat_history) >= 3 else str(chat_history)}

    TASK:
    Analyze the user's message and determine their intent. Respond with ONLY a JSON object in this exact format:

    {{
        "intent": "CREATE_PLAN" | "REGENERATE_PLAN" | "ANSWER_DURATION" | "GENERAL_QUESTION",
        "confidence": 0.0-1.0,
        "duration": <number or null>,
        "meals_per_day": <number or null>,
        "feedback": "<user's feedback text or null>",
        "reasoning": "<brief explanation>"
    }}

    INTENT DEFINITIONS:
    - CREATE_PLAN: User wants to create/generate a NEW diet plan (e.g., "make me a plan", "create diet", "I need a meal plan")
    - REGENERATE_PLAN: User wants to MODIFY/CHANGE the existing pending plan (e.g., "I don't have paneer", "replace chicken", "avoid eggs", "change this")
    - ANSWER_DURATION: User is answering a duration question with a number (only if last_was_duration_question is True)
    - GENERAL_QUESTION: Any other nutrition-related question or conversation

    EXTRACTION RULES:
    - Extract duration if mentioned (e.g., "3 days", "7 day plan", just "5")
    - Extract meals_per_day if mentioned (e.g., "4 meals", "3 meals per day")
    - For REGENERATE_PLAN, put the full user message in "feedback" field
    - Be smart: "I don't have X" = REGENERATE_PLAN, "make me a plan" = CREATE_PLAN

    Respond with ONLY the JSON, no other text.
    """
        
    try:
        import json
        import re
        
        response = get_groq_client().chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are a precise JSON response agent. Always respond with valid JSON only, no markdown, no code blocks."},
                {"role": "user", "content": intent_prompt}
            ],
            temperature=0.2
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Try to extract JSON if wrapped in code blocks or markdown
        json_match = re.search(r'\{[^{}]*"intent"[^{}]*\}', response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group(0)
        
        # Parse JSON
        intent_data = json.loads(response_text)
        
        # Validate required fields
        if "intent" not in intent_data:
            raise ValueError("Missing 'intent' field in response")
        
        return intent_data
    
    except Exception as e:
        # Fallback to general question if parsing fails
        return {
            "intent": "GENERAL_QUESTION",
            "confidence": 0.5,
            "duration": None,
            "meals_per_day": None,
            "feedback": None,
            "reasoning": f"Error parsing intent: {str(e)}"
        }

def analyze_user_request(user_feedback, previous_cost=None, duration=None):
    """
    Request Analysis Agent - Fully AI-driven interpretation of user requests
    Returns structured analysis that guides plan generation
    """
    if not user_feedback:
        return {
            "cost_target": None,
            "cost_adjustment": "maintain",
            "items_to_avoid": [],
            "items_to_include": [],
            "preferences": [],
            "constraints": [],
            "reasoning": "No feedback provided"
        }
    
    analysis_prompt = f"""
    You are a Request Analysis Agent for a Nutrition Planning System.

    USER FEEDBACK: "{user_feedback}"
    {f"PREVIOUS PLAN COST: ₹{previous_cost} for {duration} days" if previous_cost else "NO PREVIOUS PLAN"}
    {f"DURATION: {duration} days" if duration else ""}

    YOUR TASK:
    Analyze the user's request completely and provide a structured analysis. Respond with ONLY a JSON object in this exact format:

    {{
        "cost_target": <number or null>,
        "cost_adjustment": "increase" | "decrease" | "maintain" | "target",
        "items_to_avoid": ["item1", "item2"],
        "items_to_include": ["item1", "item2"],
        "preferences": ["preference1", "preference2"],
        "constraints": ["constraint1", "constraint2"],
        "reasoning": "brief explanation of your analysis"
    }}

    ANALYSIS GUIDELINES:

    1. COST ANALYSIS:
    - If user mentions a SPECIFIC amount (e.g., "cut to 200", "make it 500", "₹300"):
        → Extract the number and set "cost_target" to that value
        → Set "cost_adjustment" to "target"
    - If user says cost is too high/expensive/reduce:
        → Set "cost_adjustment" to "decrease"
        → If previous_cost exists, suggest 20-30% reduction
    - If user says they have budget/increase/premium:
        → Set "cost_adjustment" to "increase"
    - If no cost mention: "maintain"

    2. ITEMS TO AVOID:
    - Extract any items user doesn't want/have/like
    - Examples: "don't have paneer" → ["paneer"]
    - "avoid eggs" → ["eggs"]
    - "no chicken" → ["chicken"]

    3. ITEMS TO INCLUDE:
    - Extract any items user specifically wants
    - Examples: "include more vegetables" → ["vegetables"]
    - "add fish" → ["fish"]

    4. PREFERENCES:
    - Extract dietary preferences, cuisine preferences, meal timing, etc.
    - Examples: "spicy food" → ["spicy"]
    - "light breakfast" → ["light breakfast"]

    5. CONSTRAINTS:
    - Extract any other constraints
    - Examples: "less oil" → ["less oil"]
    - "more protein" → ["more protein"]

    6. REASONING:
    - Brief explanation of how you interpreted the request

    CRITICAL: 
    - Be thorough and extract ALL information from the user's request
    - If user says "cut cost to 200", cost_target MUST be 200
    - Understand context: "I don't have X" means avoid X
    - Be smart about synonyms and variations

    Respond with ONLY the JSON, no other text.
    """
    
    try:
        import json
        import re
        
        response = get_groq_client().chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are a precise JSON response agent. Always respond with valid JSON only, no markdown, no code blocks."},
                {"role": "user", "content": analysis_prompt}
            ],
            temperature=0.2
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Try to extract JSON if wrapped in code blocks or markdown
        json_match = re.search(r'\{[^{}]*"cost_target"[^{}]*\}', response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group(0)
        
        # Parse JSON
        analysis = json.loads(response_text)
        
        # Validate required fields
        required_fields = ["cost_target", "cost_adjustment", "items_to_avoid", "items_to_include", "preferences", "constraints", "reasoning"]
        for field in required_fields:
            if field not in analysis:
                if field == "cost_target":
                    analysis[field] = None
                elif field in ["items_to_avoid", "items_to_include", "preferences", "constraints"]:
                    analysis[field] = []
                elif field == "cost_adjustment":
                    analysis[field] = "maintain"
                else:
                    analysis[field] = ""
        
        return analysis
    
    except Exception as e:
        # Fallback analysis
        return {
            "cost_target": None,
            "cost_adjustment": "maintain",
            "items_to_avoid": [],
            "items_to_include": [],
            "preferences": [],
            "constraints": [],
            "reasoning": f"Error analyzing request: {str(e)}"
        }

def generate_plan_workflow(email, age, weight, height, gender, act, goal, duration, cuisine, diet, allergy, meals_per_day, feedback=None, previous_cost=None):
    """
    This function runs the entire Multi-Agent Chain.
    It returns the Final Plan Text and the Total Cost.
    feedback: Optional user feedback to incorporate into plan generation (e.g., "I don't have paneer", "cost is too high")
    previous_cost: Optional previous plan cost for relative cost adjustment
    """
    
    with st.status("🕵️ Agent Panel Coordinating...", expanded=True) as status:

        st.write("🔍 Request Analysis Agent: Analyzing User Request...")
        
        # Request Analysis Agent - Fully AI-driven interpretation
        request_analysis = analyze_user_request(feedback, previous_cost, duration)
        
        st.write("👨‍⚕️ Doctor Agent: Setting Metabolic Targets...")
        
        tdee = calculate_needs(u_data[6], u_data[5], u_data[3], u_data[4], u_data[8])
        tpro = calculate_protein(u_data[6])
        target_cals = tdee + 300 if "Gain" in goal else tdee - 400 if "Loss" in goal else tdee

        doc_prompt = f"""
        User: {u_data[3]}yo, Current weight:{u_data[6]}kg, Goal: {u_data[7]}, Activity: {u_data[8]}, Target{target_cals}kcal.
        Task: Validate these metrics.
        """
        doc_output = run_agent("Doctor Agent", "You are a strict Clinical Doctor.", doc_prompt)
    
        st.write("👨‍🍳 Chef Agent: Designing Complete Meals...")
        
        # Build Chef Agent prompt from Request Analysis Agent output
        cost_guidance = ""
        if request_analysis["cost_target"]:
            cost_guidance = f"""
        
        ***MANDATORY COST TARGET (from Request Analysis):***
        - Target Cost: ₹{request_analysis["cost_target"]} total for {duration} days
        - Daily Budget: ₹{request_analysis["cost_target"]/duration:.2f} per day
        - This is a STRICT REQUIREMENT - design meals within this budget
        - Split ₹{request_analysis["cost_target"]/duration:.2f} across {meals_per_day} meals per day
        - Use budget-friendly ingredients: Dal, Eggs, seasonal vegetables, basic staples
        - AVOID expensive items: Paneer, Chicken, exotic vegetables, premium items
        """
        elif request_analysis["cost_adjustment"] == "decrease" and previous_cost:
            target_reduction = int(previous_cost * 0.75)
            cost_guidance = f"""
        
        ***COST REDUCTION REQUIRED (from Request Analysis):***
        - Previous cost: ₹{previous_cost}
        - Target: Reduce to approximately ₹{target_reduction} or less (20-30% reduction)
        - Use budget-friendly ingredients and avoid expensive items
        """
        elif request_analysis["cost_adjustment"] == "increase" and previous_cost:
            target_increase = int(previous_cost * 1.2)
            cost_guidance = f"""
        
        ***COST INCREASE ALLOWED (from Request Analysis):***
        - Previous cost: ₹{previous_cost}
        - You can increase to ₹{target_increase} or more
        - Include premium ingredients, variety, better quality items
        """
        
        items_guidance = ""
        if request_analysis["items_to_avoid"]:
            items_guidance += f"""
        
        ***ITEMS TO AVOID (from Request Analysis):***
        - DO NOT include these items: {", ".join(request_analysis["items_to_avoid"])}
        - Find healthy, nutritionally equivalent alternatives
        """
        
        if request_analysis["items_to_include"]:
            items_guidance += f"""
        
        ***ITEMS TO INCLUDE (from Request Analysis):***
        - Prioritize including: {", ".join(request_analysis["items_to_include"])}
        """
        
        preferences_guidance = ""
        if request_analysis["preferences"]:
            preferences_guidance = f"""
        
        ***PREFERENCES (from Request Analysis):***
        - User preferences: {", ".join(request_analysis["preferences"])}
        - Incorporate these preferences into meal design
        """
        
        constraints_guidance = ""
        if request_analysis["constraints"]:
            constraints_guidance = f"""
        
        ***CONSTRAINTS (from Request Analysis):***
        - Additional constraints: {", ".join(request_analysis["constraints"])}
        - Respect all constraints while maintaining nutrition
        """
        
        analysis_summary = f"""
        
        ***REQUEST ANALYSIS SUMMARY:***
        {request_analysis["reasoning"]}
        """
        
        chef_prompt = f"""
        Cuisine: {u_data[13]}. Diet: {u_data[10]}. Allergies: {u_data[12]}.

        The user explicitly requested **{meals_per_day} MEALS PER DAY**.
        You must split the diet into exactly {meals_per_day} distinct meals.
        
        CRITICAL INSTRUCTION:
        1. DO NOT suggest single items (e.g., just "Roti").
        2. Suggest COMPLETE MEALS. 
            - Example: "2 Rotis + Palak Paneer + Cucumber Salad + 1 Glass of Milk".
        3. Mandatory:Ensure High Variety! Make sure to include a variety of items in the plan.
        
        {analysis_summary}
        {cost_guidance}
        {items_guidance}
        {preferences_guidance}
        {constraints_guidance}
        
        Task: Draft a varied menu structure for {duration} days based on the Request Analysis Agent's interpretation above.
        """
        chef_output = run_agent("Chef Agent", "You are an Indian Home Chef. You hate boring foods and you are creative and innovative and avoid unhealthy foods and dirty bulking, Meals should be meaningful and choose items quantities wisely that they have to reach the Target of {target_cals}kcal for single day(e.g category of avoiding foods: fried foods, junk foods, oil foods, processed foods etc.).", chef_prompt)

        st.write("💰 Planner & Budget Agent: Optimizing Shopping List...")
        
        # Build Budget Agent prompt from Request Analysis Agent output
        budget_cost_guidance = ""
        if request_analysis["cost_target"]:
            budget_cost_guidance = f"""
        
        ***MANDATORY COST TARGET (from Request Analysis Agent):***
        - Target Cost: ₹{request_analysis["cost_target"]} total for {duration} days
        - Daily Budget: ₹{request_analysis["cost_target"]/duration:.2f} per day
        - This is a STRICT REQUIREMENT - your final ### TOTAL_COST: ### MUST be approximately ₹{request_analysis["cost_target"]}
        - Acceptable range: ₹{int(request_analysis["cost_target"]-50)} to ₹{int(request_analysis["cost_target"]+50)}
        - Calculate every ingredient and quantity to match this target
        - If your calculation doesn't match, REVISE until it does
        """
        elif request_analysis["cost_adjustment"] == "decrease" and previous_cost:
            target_reduction = int(previous_cost * 0.75)
            budget_cost_guidance = f"""
        
        ***COST REDUCTION REQUIRED (from Request Analysis Agent):***
        - Previous cost: ₹{previous_cost}
        - Target: Reduce to approximately ₹{target_reduction} or less (20-30% reduction)
        - Use budget-friendly ingredients: Dal, Eggs, seasonal vegetables, basic staples
        - Avoid expensive items: Paneer, Chicken, exotic vegetables, premium items
        - Maintain protein with cheaper alternatives (Dal, Eggs, Soya)
        """
        elif request_analysis["cost_adjustment"] == "increase" and previous_cost:
            target_increase = int(previous_cost * 1.2)
            budget_cost_guidance = f"""
        
        ***COST INCREASE ALLOWED (from Request Analysis Agent):***
        - Previous cost: ₹{previous_cost}
        - You can increase to ₹{target_increase} or more
        - Include premium ingredients, variety, better quality items
        """
        elif previous_cost:
            budget_cost_guidance = f"""
        
        ***PREVIOUS PLAN REFERENCE:***
        - Previous cost: ₹{previous_cost} for {duration} days
        - Maintain similar cost range unless otherwise specified
        """
        
        budget_items_guidance = ""
        if request_analysis["items_to_avoid"]:
            budget_items_guidance += f"""
        
        ***ITEMS TO AVOID (from Request Analysis Agent):***
        - DO NOT include: {", ".join(request_analysis["items_to_avoid"])}
        - Find nutritionally equivalent, cost-effective alternatives
        """
        
        if request_analysis["items_to_include"]:
            budget_items_guidance += f"""
        
        ***ITEMS TO INCLUDE (from Request Analysis Agent):***
        - Prioritize: {", ".join(request_analysis["items_to_include"])}
        """
        
        budget_constraints_guidance = ""
        if request_analysis["constraints"]:
            budget_constraints_guidance = f"""
        
        ***CONSTRAINTS (from Request Analysis Agent):***
        - Additional constraints: {", ".join(request_analysis["constraints"])}
        - Respect all constraints while optimizing cost
        """
        
        budget_prompt = f"""
        Duration: {duration} Days.
        Menu Concept: {chef_output}
        
        {analysis_summary}
        {budget_cost_guidance}
        {budget_items_guidance}
        {budget_constraints_guidance}
        
        REALITY CHECK:
        1. Assume user has Salt, Oil, Turmeric, & Spices.
        2. Budget for MAIN ingredients: Atta, Rice, Vegetables, Dal, Eggs/Paneer/Chicken, Milk, Curd.
        3. Market Rates: Eggs ₹7, Milk ₹32/500ml, Chicken ₹280/kg, Paneer ₹100/200g, Veg ₹40-60/kg.
        (use these items as only reference and not as you only have these items in the market, you can use wide range of items as well, but only healthy and nutritious items)
        
        CRITICAL INSTRUCTION:
        Every single item in the daily plan MUST HAVE A QUANTITY.
        - BAD: "display only items"
        - GOOD: "display items with quantities"

        ***EXTREMELY IMPORTANT - COST CALCULATION:*** 
            {f"TARGET COST: ₹{request_analysis['cost_target']} - Your final cost MUST be approximately ₹{request_analysis['cost_target']} (within ₹50 range)" if request_analysis["cost_target"] else "Calculate the total cost accurately based on all ingredients and quantities"}
            
            At the very end of your response, output the total cost in this EXACT format:
            ### TOTAL_COST: 1500 ###
            (Replace 1500 with your calculated number. Only digits. No other text in this line.)
            
            COST CALCULATION PROCESS:
            1. List ALL ingredients needed for {duration} days
            2. Calculate quantity needed for each ingredient
            3. Multiply quantity × market rate for each item
            4. Sum ALL costs to get total
            5. {f"VERIFY: Total should be approximately ₹{request_analysis['cost_target']}. If not, adjust quantities and recalculate." if request_analysis["cost_target"] else "Double-check your math"}
        
        Task:
        1. Create a CONSOLIDATED GROCERY LIST for {duration} days.
        2. Calculate TOTAL ESTIMATED COST based on Request Analysis Agent's interpretation above.
        3. {f"ENSURE total cost is approximately ₹{request_analysis['cost_target']}" if request_analysis["cost_target"] else "Calculate accurately"}
        4. Write the Final Meal Plan (Day 1 to {duration}) WITH QUANTITIES.
        """
        
        # Dynamic agent persona - adapts based on Request Analysis Agent output
        if request_analysis["cost_target"]:
            agent_persona = f"""You are a PRECISE Budget Manager with a MANDATORY COST TARGET.
            CRITICAL MISSION: Create a meal plan that costs EXACTLY ₹{request_analysis['cost_target']} total (approximately ₹{request_analysis['cost_target']/duration:.2f} per day).
            - Your calculated ### TOTAL_COST: ### MUST be close to ₹{request_analysis['cost_target']} (within ₹50 range)
            - Every ingredient and quantity choice must align with this budget
            - Calculate carefully: if your cost doesn't match, REVISE your plan
            - Maintain nutritional balance and target calories of {target_cals} per day within this strict budget
            - This is NOT a suggestion - it's a REQUIREMENT from the Request Analysis Agent"""
        else:
            agent_persona = f"""You are an Intelligent Budget & Nutrition Manager. 
            Your role is to follow the Request Analysis Agent's interpretation and optimize the meal plan accordingly.
            - Follow the cost adjustment guidance from Request Analysis Agent
            - Respect items to avoid/include from Request Analysis Agent
            - Always maintain nutritional balance and ensure meals reach target calories of {target_cals} per day
            - Be adaptive based on the Request Analysis Agent's structured output"""
         
        plan_text = run_agent(
            "Planner, while calculating and arranging items be realistc & Budget Agent",
            agent_persona,
            budget_prompt
        )

        # ---------- CALORIE CORRECTION LOOP ----------
        for attempt in range(MAX_RETRIES):
            total_calories = extract_calories(plan_text)
            gap = target_cals - total_calories

            # Acceptable range
            if abs(gap) <= CAL_TOLERANCE:
                break

            correction_prompt = f"""
            You generated the following meal plan:

            {plan_text}

            CALORIE CHECK FAILED:
            - Current total calories: {total_calories}
            - Target calories: {target_cals}
            - Difference: {gap} kcal

            TASK:
            - DO NOT redesign the plan
            - ONLY adjust quantities OR add/remove 1–2 simple foods
            - Keep meals realistic and affordable
            - Return the FULL corrected meal plan
            - Ensure final calories are within ±{CAL_TOLERANCE} kcal
            """

            plan_text = run_agent(
                "Calorie Correction Agent",
                "You are correcting a meal plan to meet calorie targets accurately.",
                correction_prompt
            )
            
        
        cost_match = re.search(r"###\s*TOTAL_COST:\s*([\d,]+)", plan_text)
        extracted_cost = cost_match.group(1).replace(",", "") if cost_match else "0"
        final_cost=extracted_cost
    
    
    
        st.write("🤵 Manager Agent: Formatting...")
        manager_prompt = f"""
        Compile this into a user-friendly plan.
        Doctor Targets: {doc_output}
        Final Cost: {extracted_cost}
        Final Plan: {plan_text}
        
        FORMAT:
        1. 🎯 HEALTH TARGETS
            - Objective: (if {u_data[6]} <= {u_data[7]} then weight gain; else weight lose)
            - Current weight:{u_data[6]}
            - Weight goal:{u_data[7]}
            - Daily required calories for user to reach goal:{target_cals}
            - Daily required protein for user to reach goal:{tpro}
        2. 🛍️ SHOPPING LIST
        3. 📅 DAILY MEAL PLAN
        4. 🔢 Total calculations of the micros and macros
            (IMPORTANT: Your calorie calculations will be programmatically verified. 
            If under {target_cals}, the system will auto-correct. Be accurate.)
            - Day 1:
                - Breakfast: [Dish] ([Quantity])
                - Lunch: Xcalories, Ygm protein, etc...
                - Dinner: Xcalories, Ygm protein, etc...
                - Snacks: should be healthy and not repetative regularly
                - #Total: X calories, Y gm protein, Z gm carbs, W gm fats for that day
        5. 💰 TOTAL COST
            (Display a warning about prices are not so accurate it may vary in real world)
            IMPORTANT: Include the total cost in this EXACT format at the end:
            # Total Budget For Plan: [₹number] 
            (e.g., ### Total Budget For Plan: [₹number] ###)
        6.  FINAL VERDICT (it should be about meal and give message to consult a doctor if needed)
        """
        final_output = run_agent("Manager Agent", "You are a Helpful Assistant.", plan_text + "\n\n" + manager_prompt)
        
        
        # final_output = enforce_minimum_calories(final_output, target_cals, tpro)
        
        status.update(label="✅ Strategy Finalized!", state="complete", expanded=True)

        # --- IMPROVED EXTRACTION LOGIC ---
        # Search in both plan_output and final_output with multiple patterns
        extracted_cost = "0"

        # Pattern 1: Exact format with ### markers
        patterns = [
            r"###\s*TOTAL_COST:\s*([\d,]+)\s*###",  # With closing ###
            r"###\s*TOTAL_COST:\s*([\d,]+)",        # Without closing ###
            r"TOTAL_COST:\s*([\d,]+)",              # Without ### markers
            r"Total Cost[:\s]+₹?\s*([\d,]+)",       # Natural language format
            r"Total[:\s]+₹?\s*([\d,]+)",            # Just "Total:"
            r"₹\s*([\d,]+)",                         # Just currency symbol
        ]

        # Search in final_output first (most likely location after formatting)
        for pattern in patterns:
            cost_match = re.search(pattern, final_output, re.IGNORECASE)
            if cost_match:
                extracted_cost = cost_match.group(1).replace(",", "").strip()
                if extracted_cost and extracted_cost.isdigit():
                    break

        # Fallback: search in plan_output if not found in final_output
        if extracted_cost == "0":
            for pattern in patterns:
                cost_match = re.search(pattern, plan_text, re.IGNORECASE)
                if cost_match:
                    extracted_cost = cost_match.group(1).replace(",", "").strip()
                    if extracted_cost and extracted_cost.isdigit():
                        break

        st.session_state['current_strategy'] = final_output
        st.session_state['total_budget'] = extracted_cost
        st.session_state['agent_memory'].update({
            "meal_plan": final_output,
            "plan_duration": duration,
            "total_budget": extracted_cost
        })

    return final_output, final_cost

def refine_plan_with_feedback(current_plan, feedback_msg):
    prompt = f"""
    The user REJECTED the previous plan.
    Previous Plan Summary: {current_plan[:1000]}...

    User Feedback: "{feedback_msg}"

    TASK: Completely rewrite the plan to address this feedback. 
    Keep the calculation logic in mind but change the meals/ingredients as requested.
    Maintain the same structured format (Breakfast, Lunch, Dinner, Cost).
    """
    return run_agent("Manager Agent", "You are an adaptive nutritionist. Fix the plan based on feedback.", prompt)

def live_chat_reply(history, user_context):
    system_msg = (
        "You are a friendly, detailed nutrition assistant. "
        f"Context on User: {user_context} "
        "Your responses must be fully complete. "
        "Write at least 5-8 sentences with explanations and guidance. "
        "If food diary entries conflict with the planned diet, politely point it out and suggest corrections."
        "If the user asks about their plan, refer to the 'Approved Plan' context provided."
    )

    recent_history = history[-4:]

    # Convert session history to Groq format
    messages = [{"role":"system", "content": system_msg}] + recent_history

    resp = get_groq_client().chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=messages,
        max_tokens=800,
        temperature=0.7
    )
    return resp.choices[0].message.content

def analyze_image(uploaded_file):
    img = Image.open(uploaded_file)
    response = genai_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=["Identify this food in an Indian context. Estimate calories and macros.", img]
    )
    return response.text

def estimate_food_carbon(food_text):
    """
    Rough per-meal CO2e estimator (kg CO2e)
    Based on global LCA averages.
    """

    text = food_text.lower()

    if any(x in text for x in ["mutton", "lamb", "beef"]):
        return 2.5   # very high impact per meal
    if any(x in text for x in ["chicken"]):
        return 0.8
    if any(x in text for x in ["paneer", "cheese", "butter"]):
        return 0.6
    if any(x in text for x in ["egg"]):
        return 0.4
    if any(x in text for x in ["fish"]):
        return 0.5
    if any(x in text for x in ["dal", "lentil", "beans"]):
        return 0.2
    if any(x in text for x in ["vegetable", "sabzi", "salad"]):
        return 0.15
    if any(x in text for x in ["rice", "roti", "chapati"]):
        return 0.25

    # default unknown mixed meal
    return 0.35

# --- 4. CSS ---
st.markdown("""
<style>
    div[data-testid="stDialog"] {
        backdrop-filter: blur(10px) !important;
        background-color: rgba(0, 0, 0, 0.4) !important;
    }

    .chat-scroll {
    max-height: 420px;
    overflow: scroll;
    padding-right: 10px;
    }

</style>
""", unsafe_allow_html=True)

# --- 5. UI FLOW ---
if (
    cookies.get("user_email")
    and not st.session_state.get("logged_in")
    and not st.session_state.get("force_logged_out", False)
):
    user = get_user_by_email(cookies.get("user_email"))
    if user:
        st.session_state['logged_in'] = True
        st.session_state['user_info'] = user

if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if 'user_info' not in st.session_state: st.session_state['user_info'] = None
if 'pending_plan' not in st.session_state: st.session_state['pending_plan'] = None
if 'feedback_mode' not in st.session_state: st.session_state['feedback_mode'] = False
if 'live_chat' not in st.session_state: st.session_state['live_chat'] = []

# --- GLOBAL AGENT MEMORY ---
if 'agent_memory' not in st.session_state:
    st.session_state['agent_memory'] = {
        "meal_plan": None,
        "plan_duration": None,
        "total_budget": None,
        "carbon_report": None,
        "carbon_metrics": None,
        "food_diary": []
    }

final_cost=0
cdays=0

# ================= POP-UP LOGIN LOGIC =================

@st.dialog("🔐 Login / Sign Up")
def login_dialog():
    tab1, tab2 = st.tabs(["Login", "Create Account"])
    
    with tab1:
        email = st.text_input("Email Address", key="login_email")
        password = st.text_input("Password", type='password', key="login_pass")
        if st.button("Login", use_container_width=True):
            if not is_valid_email(email):
                st.error("⚠️ Invalid Email Format")
            else:
                user_data = login_user(email, password)
                if user_data:
                    st.session_state['logged_in'] = True
                    st.session_state['user_info'] = user_data
                    cookies["user_email"] = email
                    cookies.save()
                    st.session_state.pop("force_logged_out", None)
                    st.success("Logged in successfully")
                    st.rerun()
                else:
                    st.error("❌ Incorrect Email or Password")

    with tab2:
        st.caption("Join for AI-Powered Health Plans")
        col1, col2 = st.columns(2)
        with col1:
            new_email = st.text_input("Email", key="signup_email")
            new_pass = st.text_input("Password", type='password', key="signup_pass")
            new_user = st.text_input("Display Name", key="signup_name")
            new_age = st.number_input("Age", 15, 90, 25, key="signup_age")
            new_gender = st.selectbox("Gender", ["Male", "Female", "Other"], key="signup_gen")
            new_allergy = st.text_input("Allergies", key="signup_allergy")
        
        with col2:
            new_height = st.number_input("Height (cm)", 100, 250, 170, key="signup_ht")
            new_weight = st.number_input("Weight (kg)", 30, 150, 70, key="signup_wt")
            new_goal_w = st.number_input("Goal Wt (kg)", 30, 150, 65, key="signup_gw")
            new_activity = st.selectbox("Activity", ["Sedentary", "Active", "Very Active"], key="signup_act")
            new_cuisine = st.text_input("Cuisine Pref", value="Indian", key="signup_cuisine")
        
        new_meals = st.slider("Meals/Day", 2, 6, 3, key="signup_meals")
        new_diet = st.selectbox("Diet Type", ["Vegetarian", "Non-Vegetarian", "Vegan"], key="signup_diet")
        new_sleep = st.slider("Sleep (Hrs)", 4.0, 12.0, 7.0, key="signup_sleep")

        if st.button("Sign Up", use_container_width=True):
            if not is_valid_email(new_email):
                st.error("⚠️ Invalid Email")
            elif len(new_pass) < 4:
                st.error("⚠️ Password too short")
            else:
                if add_user(new_email, new_user, new_pass, new_age, new_gender, new_height, new_weight, new_goal_w, new_activity, new_meals, new_diet, new_sleep, new_allergy, new_cuisine):
                    st.success("✅ Account Created! Please Login.")
                else:
                    st.error("❌ Email already registered.")

# ================= MAIN APP =================

if not st.session_state['logged_in']:
    st.title("🥗 Agentic Nutrition Planner")
    st.markdown("### Your Personal AI Health Strategist")
    st.write("Calculates Budget • Tracks Macros • Adapts to You")
    st.markdown("---")
    if st.button("🚀 Get Started / Login", type="primary", use_container_width=True):
        login_dialog()

else:
    u_data = st.session_state['user_info']
    st.sidebar.title(f"👤 {u_data[1]}")
    st.sidebar.caption(f"ID: {u_data[0]}")
    
    with st.sidebar.expander("📝 Edit Profile"):
        e_age = st.number_input("Age", value=u_data[3], key="edit_age")
        e_weight = st.number_input("Weight", value=u_data[6], key="edit_weight")
        e_goal = st.number_input("Goal Weight", value=u_data[7], key="edit_goal")
        
        e_activity_list = ["Sedentary", "Active", "Very Active"]
        curr_act = u_data[8] if u_data[8] in e_activity_list else "Sedentary"
        e_activity = st.selectbox("Activity", e_activity_list, index=e_activity_list.index(curr_act), key="edit_act")
        
        e_diet_list = ["Vegetarian", "Non-Vegetarian", "Vegan"]
        curr_diet = u_data[10] if u_data[10] in e_diet_list else "Vegetarian"
        e_diet = st.selectbox("Diet Type", e_diet_list, index=e_diet_list.index(curr_diet), key="edit_diet")
        
        e_allergy = st.text_input("Allergies", value=u_data[12], key="edit_allergy")
        e_cuisine = st.text_input("Cuisine", value=u_data[13], key="edit_cuisine")

        if st.button("Update Profile"):
            update_user_profile(u_data[0], e_age, u_data[4], u_data[5], e_weight, e_goal, e_activity, u_data[9], e_diet, u_data[11], e_allergy, e_cuisine)
            st.session_state['user_info'] = get_user_by_email(u_data[0]) 
            st.success("Updated!")

        with st.sidebar.expander("📚 Your Diet History"):
            approved = get_approved_plans(u_data[0])
            if not approved: st.caption("No plans yet.")
            for i, (ts, plan) in enumerate(approved, 1):
                if st.button(f"📅 Plan {ts[:10]}", key=f"hist_{i}"):
                    st.session_state['pending_plan'] = plan # Load old plan into view
                    st.success("Loaded plan into view.")

    st.sidebar.markdown("---")
    st.sidebar.button(
        "🚪 Logout",
        key="sidebar_logout_btn",
        on_click=logout
    )
        
    with st.sidebar.expander("⚠️ Danger Zone"):
        if st.button("Delete My Account", type="primary"):
            delete_user_account(u_data[0])
            st.session_state.clear()
            st.success("Account Deleted.")
            st.rerun()

    # --- MAIN CONTENT ---
    st.title("🥗 Agentic Nutrition Planner")
    st.caption(f"Multi-Agent System | {e_diet} | {e_cuisine} | {e_age} Years")

    tab1, tab2, tab3 = st.tabs(["🗓️ Strategic Planner", "📸 Visual Tracker", "🌍 Carbon Footprint"])

    with tab1:
        if not st.session_state['feedback_mode']:
            st.header("Generate Strategy")
            col1, col2 = st.columns(2)
            with col1:
                # Determine valid options based on weight math
                if e_weight > e_goal:
                    # User is heavier than goal -> Must Lose Weight
                    valid_objectives = ["Weight Loss", "General Health", "Student Survival"]
                    msg = f"📉 Goal: Lose {e_weight - e_goal:.1f} kg"
                elif e_weight < e_goal:
                    # User is lighter than goal -> Must Gain Weight
                    valid_objectives = ["Muscle Gain", "General Health", "Student Survival"]
                    msg = f"📈 Goal: Gain {e_goal - e_weight:.1f} kg"
                else:
                    # Weights are equal
                    valid_objectives = ["Maintenance", "General Health", "Student Survival"]
                    msg = "⚖️ Maintenance Mode"

                goal = st.selectbox("Objective", valid_objectives)
                st.caption(msg)
 
            with col2:
                cdays = st.number_input("Duration (Days):", 1, 7)

        is_locked = cdays > 7
        if is_locked: st.error("Duration must be less than or equals to 7 days.")

        if st.button("Forecast Plan", disabled=is_locked):
            
            # 1. Determine Goal
            obj = "Weight Loss" if u_data[6] > u_data[7] else "Muscle Gain"

            # 2. Run Workflow (NO DISPLAYING TEXT HERE)
            final_plan, cost = generate_plan_workflow(
                u_data[0], u_data[3], u_data[6], u_data[5], u_data[4], u_data[8], 
                obj, cdays, u_data[13], u_data[10], u_data[12], u_data[9]
            )

            # 3. STRICT REPLACEMENT: Overwrite any existing pending plan
            st.session_state['pending_plan'] = final_plan
            st.session_state['total_budget'] = cost
            st.session_state['plan_duration'] = cdays  # Store duration for regeneration
            
            # 4. RESET FEEDBACK MODE (Crucial: If they were editing an old plan, cancel that mode)
            st.session_state['feedback_mode'] = False
            
            # 5. RERUN to let the Main Display Block handle the rendering
            # st.rerun()

        
        # --- SINGLE SOURCE OF TRUTH FOR DISPLAYING PLANS ---
        if st.session_state['pending_plan']:
            st.markdown("---")
            st.subheader("📋 Proposed Strategy")
            
            # This is the ONLY place the plan text is printed to the screen
            st.info(st.session_state['pending_plan'])
            
            with st.container(border=True):
                st.markdown("### 💰 Financial Forecast")

                left, spacer, right = st.columns([2, 1, 2])

                try:
                    budget_str = str(st.session_state.get("total_budget", "0"))
                    budget_clean = re.sub(r"[^\d.]", "", budget_str)
                    total_cost = float(budget_clean) if budget_clean else 0.0
                    duration = st.session_state.get("plan_duration", 1)

                    if total_cost > 0:
                        left.metric(
                            "Total Cost",
                            f"₹{total_cost:,.0f}"
                        )

                        right.metric(
                            "Daily Average",
                            f"₹{total_cost / duration:,.0f} / day"
                        )
                    else:
                        left.metric("Total Cost", "₹--")
                        right.metric("Daily Average", "₹--")

                except Exception:
                    left.metric("Total Cost", "₹--")
                    right.metric("Daily Average", "₹--")
            
            # ACTION BUTTONS (Only if not in feedback mode)
            if not st.session_state['feedback_mode']:
                b1, b2, b3 = st.columns(3)
                with b1:
                    # APPROVE: Store in DB
                    if st.button("👍 Approve & Save Plan", type="primary", use_container_width=True):
                        save_diet_plan(u_data[0], st.session_state['pending_plan'], "approved")
                        get_latest_approved_context.clear() # Refresh Chat Context
                        st.success("✅ Plan Saved to History!")
                        st.session_state['pending_plan'] = None # Remove from Pending view
                        st.success("✅ Plan Saved to History!")

                with b2:
                    # WIP: Order Grocery List (Future)
                    if st.button("Approve & Order The List", use_container_width=True):
                        st.error("Currently implementing this module")
                
                with b3:
                    # REJECT: Do NOT Store in DB. Trigger Refinement.
                    if st.button("👎 Reject & Refine", use_container_width=True):
                        st.session_state['feedback_mode'] = True # Triggers the chat input at bottom
                        st.success("You can now provide feedback below to refine the plan.")

    # --- INTELLIGENT CHAT SYSTEM ---
    
    if st.session_state['feedback_mode']:
        st.warning("📝 Feedback Mode: Why did you reject the plan?")
        feedback_msg = st.chat_input("Ex: 'I don't like Tofu', 'Too expensive'...")
        if feedback_msg:
            stored_duration = st.session_state.get("plan_duration", 7)

        # Previous cost (for relative adjustment)
            prev_cost_raw = st.session_state.get("total_budget", "0")
            try:
                prev_cost_clean = re.sub(r"[^\d.]", "", str(prev_cost_raw))
                previous_cost = float(prev_cost_clean) if prev_cost_clean else None
            except:
                previous_cost = None

            # --- REGENERATE PLAN ---
            with st.status("🔄 Regenerating plan based on your feedback...", expanded=True):
                obj = "Weight Loss" if u_data[6] > u_data[7] else "Muscle Gain"

                final_plan, cost = generate_plan_workflow(
                    u_data[0], u_data[3], u_data[6], u_data[5], u_data[4], u_data[8],
                    obj,
                    stored_duration,
                    u_data[13],
                    u_data[10],
                    u_data[12],
                    u_data[9],
                    feedback=feedback_msg,
                    previous_cost=previous_cost
                )

            # --- UPDATE STATE ---
            st.session_state['pending_plan'] = final_plan
            st.session_state['total_budget'] = cost
            st.session_state['feedback_mode'] = False

            st.success("✅ Plan regenerated based on your feedback.")
            # st.rerun()

    else:
        # Display Chat History
        if st.session_state['live_chat']:
            with st.expander("💬 Chat History", expanded=False):
                st.markdown('<div class="chat-scroll">', unsafe_allow_html=True)

                for msg in st.session_state['live_chat']:
                    with st.chat_message(msg["role"]):
                        st.write(msg["content"])

                st.markdown('</div>', unsafe_allow_html=True)

        # --- THE SMART INPUT ---
        user_msg = st.chat_input("Ask a question OR type 'Make me a diet plan'...")
        
        if user_msg:
            # 1. Add User Message to UI
            st.session_state['live_chat'].append({"role": "user", "content": user_msg})
            
            # 2. AI-POWERED INTENT DETECTION
            has_pending_plan = st.session_state.get('pending_plan') is not None
            intent_data = detect_user_intent(user_msg, st.session_state['live_chat'], has_pending_plan)
            
            intent = intent_data.get("intent", "GENERAL_QUESTION")
            duration = intent_data.get("duration")
            req_meals = intent_data.get("meals_per_day") or u_data[9]
            feedback_text = intent_data.get("feedback")
            
            # 3. DYNAMIC ROUTING BASED ON DETECTED INTENT
            if intent == "CREATE_PLAN":
                # User wants to create a new plan
                if duration:
                    if duration > 7:
                        st.session_state['live_chat'].append({"role": "assistant", "content": "⚠️ Limit is 7 days. Generating a 7-day plan..."})
                        duration = 7
                    if duration < 1:
                        duration = 1

                    # Generate new plan
                    with st.status(f"👨‍🍳 Designing {req_meals}-Meal Strategy for {duration} Days...", expanded=True) as status:
                        obj = "Weight Loss" if u_data[6] > u_data[7] else "Muscle Gain"
                        final_plan, cost = generate_plan_workflow(
                            u_data[0], u_data[3], u_data[6], u_data[5], u_data[4], u_data[8], 
                            obj, duration, u_data[13], u_data[10], u_data[12], req_meals
                        )
                    status.update(label="✅ Strategy Ready!", state="complete", expanded=False)
                    
                    # Store plan
                    st.session_state['pending_plan'] = final_plan
                    st.session_state['total_budget'] = cost
                    st.session_state['plan_duration'] = duration
                    st.session_state['feedback_mode'] = False
                    
                    st.session_state['live_chat'].append({"role": "assistant", "content": f"✅ I've created a new {duration}-day plan. Check the 'Proposed Strategy' section above."})
                    # st.rerun()
                    st.success("Plan generated and displayed above.")
                else:
                    # No duration specified, ask for it
                    reply = "How many days should I plan for?"
                    st.session_state['live_chat'].append({"role": "assistant", "content": reply})
                    # st.rerun()
                    st.success("Asked for duration.")
            
            elif intent == "ANSWER_DURATION":
                # User is answering a duration question
                try:
                    if duration:
                        if duration > 7: duration = 7
                        if duration < 1: duration = 1
                        
                        with st.status(f"🚀 Crafting {duration}-Day Strategy...", expanded=True) as status:
                            obj = "Weight Loss" if u_data[6] > u_data[7] else "Muscle Gain"
                            final_plan, cost = generate_plan_workflow(
                                u_data[0], u_data[3], u_data[6], u_data[5], u_data[4], u_data[8], 
                                obj, duration, u_data[13], u_data[10], u_data[12], u_data[9]
                            )
                        status.update(label="✅ Strategy Finalized!", state="complete", expanded=False)
                        
                        st.session_state['pending_plan'] = final_plan
                        st.session_state['total_budget'] = cost
                        st.session_state['plan_duration'] = duration
                        st.session_state['live_chat'].append({"role": "assistant", "content": "✅ Plan generated! You can review it above."})
                        # st.rerun()
                        st.success()
                    else:
                        raise ValueError("No duration extracted")
                except:
                    reply = "I need a number (1-7). How many days?"
                    st.session_state['live_chat'].append({"role": "assistant", "content": reply})
                    # st.rerun()
                    st.success()
            
            elif intent == "REGENERATE_PLAN":
                # User wants to modify/regenerate the existing plan
                if not has_pending_plan:
                    # No plan to regenerate, treat as general question
                    intent = "GENERAL_QUESTION"
                else:
                    stored_duration = st.session_state.get('plan_duration', 7)
                    
                    # Get previous cost for relative adjustment
                    prev_cost_str = st.session_state.get('total_budget', '0')
                    try:
                        prev_cost_clean = re.sub(r'[^\d.]', '', str(prev_cost_str))
                        previous_cost = float(prev_cost_clean) if prev_cost_clean else None
                    except:
                        previous_cost = None
                    
                    # Regenerate plan with feedback
                    with st.status(f"🔄 Regenerating Plan Based on Your Feedback...", expanded=True) as status:
                        obj = "Weight Loss" if u_data[6] > u_data[7] else "Muscle Gain"
                        final_plan, cost = generate_plan_workflow(
                            u_data[0], u_data[3], u_data[6], u_data[5], u_data[4], u_data[8], 
                            obj, stored_duration, u_data[13], u_data[10], u_data[12], u_data[9],
                            feedback=feedback_text or user_msg,
                            previous_cost=previous_cost
                        )
                    status.update(label="✅ Plan Regenerated!", state="complete", expanded=False)
                    
                    # Update the pending plan
                    st.session_state['pending_plan'] = final_plan
                    st.session_state['total_budget'] = cost
                    st.session_state['plan_duration'] = stored_duration
                    st.session_state['feedback_mode'] = False
                    
                    st.session_state['live_chat'].append({
                        "role": "assistant", 
                        "content": f"✅ I've regenerated your plan considering your feedback. Check the updated 'Proposed Strategy' section above."
                    })
                    # st.rerun()
            
            # GENERAL_QUESTION or fallback
            if intent == "GENERAL_QUESTION":
                # General Chat (Ingredients, Doubts, Etc.)
                # 1. Check if there is a PROPOSED (Pending) Plan on screen
                pending_plan = st.session_state.get('pending_plan')
                
                # 2. Check if there is a HISTORIC (Approved) Plan in DB
                approved_plan = get_latest_approved_context(u_data[0])
                
                # 3. Construct the Context based on Priority
                if pending_plan:
                    # PRIORITY: User is likely asking about the plan currently on screen
                    plan_context = f"""
                    CURRENT STATUS: User has a generated PROPOSED STRATEGY on screen (Not yet approved).
                    FOCUS: Answer questions specific to this PROPOSED plan.
                    
                    DETAILS OF PROPOSED PLAN:
                    {pending_plan[:2500]}... [truncated for length]
                    """
                else:
                    # FALLBACK: User is asking about their general diet history
                    plan_context = f"""
                    CURRENT STATUS: No active plan on screen. Referring to last approved history.
                    LAST APPROVED PLAN:
                    {approved_plan[:1500]}...
                    """

                # 4. Final Context String
                memory = st.session_state.get("agent_memory", {})
                food_logs = st.session_state['agent_memory'].get("food_diary", [])

                recent_food_log = ""
                if food_logs:
                    recent_entries = food_logs[-3:]  # last 3 meals only
                    recent_food_log = "\n".join([
                        f"- {f['timestamp']}: {f['analysis']} (🌍 {f.get('co2', 'N/A')} kg CO₂e)"
                        for f in recent_entries
                    ])
                else:
                    recent_food_log = "No food images analyzed yet."

                memory = st.session_state.get("agent_memory") or {}
                carbon = memory.get("carbon_metrics") or {}

                user_context = f"""
                USER PROFILE:
                Age: {u_data[3]}
                Weight: {u_data[6]} kg → Goal: {u_data[7]} kg
                Diet: {u_data[10]}, Cuisine: {u_data[13]}

                MEAL PLAN CONTEXT:
                {memory.get("meal_plan", "No plan generated yet.")}

                PLAN DURATION:
                {memory.get("plan_duration", "N/A")} days

                BUDGET:
                ₹{memory.get("total_budget", "N/A")}

                CARBON FOOTPRINT ANALYSIS:
                CO₂ Emissions: {carbon.get("co2", "N/A")} kg CO2e
                Sustainability Score: {carbon.get("score", "N/A")}
                Sustainability Score: {carbon.get("score", "N/A")}

                ENVIRONMENT REPORT:
                {memory.get("carbon_report", "No environmental analysis performed yet.")}

                FOOD DIARY (Visual Tracker - Recent Meals):
                {recent_food_log}
                """
                
                # 5. Get Reply
                bot_reply = live_chat_reply(st.session_state['live_chat'], user_context)
                st.session_state['live_chat'].append({"role": "assistant", "content": bot_reply})
                # st.rerun()
            

    with tab2:
        st.header("🍽️ Food Diary")

        # --- Upload image ---
        uploaded_image = st.file_uploader(
            "Upload meal photo...",
            type=["jpg", "png", "jpeg"],
            key="food_image_uploader"
        )

        # --- FIX: Only reset if the file is NEW ---
        if uploaded_image is not None:
            # Create a unique ID for the file
            file_id = f"{uploaded_image.name}_{uploaded_image.size}"
            
            # Check if this is a DIFFERENT file than before
            if st.session_state.get("last_uploaded_file_id") != file_id:
                st.session_state["current_food_image"] = uploaded_image
                st.session_state["food_analysis_done"] = False
                st.session_state["food_analysis_result"] = None
                st.session_state["last_uploaded_file_id"] = file_id # Update the ID
        else:
            # If user removed the file, clear the ID
            st.session_state["last_uploaded_file_id"] = None

        current_image = st.session_state.get("current_food_image")

        # --- Display image ---
        if current_image is not None:
            st.image(current_image, caption="Current meal under analysis", width=300)

            # --- Analyze button ---
            if st.button("Analyze", key="analyze_food_btn"):
                with st.spinner("🔍 AI is analyzing your food..."):
                    analysis_result = analyze_image(current_image)
                    st.session_state["food_analysis_result"] = analysis_result
                    st.session_state["food_analysis_done"] = True
                    
                    # Carbon estimate
                    meal_co2 = estimate_food_carbon(analysis_result)
                    
                    # Update Agent Memory immediately so Chat can see it
                    st.session_state["agent_memory"]["food_diary"].append({
                        "timestamp": datetime.datetime.now().isoformat(),
                        "analysis": analysis_result,
                        "co2": meal_co2
                    })

            # --- Show analysis ---
            if st.session_state.get("food_analysis_done"):
                st.info(st.session_state["food_analysis_result"])
                
                # Show carbon metric if available in memory
                if st.session_state["agent_memory"]["food_diary"]:
                    last_entry = st.session_state["agent_memory"]["food_diary"][-1]
                    st.caption(f"🌍 Estimated Carbon Impact: {last_entry.get('co2', 0):.2f} kg CO₂e")

                st.markdown("---")

                


    with tab3:
        st.header("🌍 Ecological Impact Of Meal")

        analysis_mode = st.radio(
            "Choose analysis source",
            ["Planned Meal (Strategy)", "Actual Meals (Photos)"],
            horizontal=True
        )

        # --- CONTEXT BUILDER ---
        # (This part is fine, keeping your existing logic)
        if analysis_mode == "Planned Meal (Strategy)":
            if 'current_strategy' not in st.session_state:
                st.warning("⚠️ Please generate a Meal Plan in the 'Strategic Planner' tab first.")
                st.stop()
            analysis_context = st.session_state['current_strategy']
            analysis_label = "PLANNED MEAL STRATEGY"
        else:
            food_logs = st.session_state['agent_memory'].get("food_diary", [])
            if not food_logs:
                st.warning("⚠️ No food photos analyzed yet. Use the Visual Tracker first.")
                st.stop()
            analysis_context = "\n".join([
                f"- {f['analysis']} (Estimated CO₂: {f.get('co2', 'N/A')} kg)"
                for f in food_logs[-5:]
            ])
            analysis_label = "ACTUAL CONSUMED MEALS"

        st.write(f"Analyze the environmental impact of **{analysis_label.lower()}**.")

        # --- FIX: Button logic ---
        if st.button("🌱 Calculate Carbon Footprint"):
            with st.status("♻️ Environmental Analyst is auditing...", expanded=True):
                # ... (Your existing prompt construction logic) ...
                eco_prompt = f"""
                You are an Environmental Scientist. Analyze: {analysis_context}
                TASK: Estimate Carbon Footprint (kg CO2e) and Score (0-100).
                OUTPUT FORMAT: ### CO2: 12.5 ### ### SCORE: 75 ###
                """
                
                eco_report = run_agent("Environmental Analyst", "You are a precise scientist.", eco_prompt)

                # Extract
                co2_match = re.search(r"###\s*CO2:\s*([\d\.]+)", eco_report)
                score_match = re.search(r"###\s*SCORE:\s*([\d]+)", eco_report)
                est_co2 = float(co2_match.group(1)) if co2_match else 0.0
                sust_score = int(score_match.group(1)) if score_match else 50
                clean_report = re.sub(r"###.*?###", "", eco_report).strip()

                # --- STORE PERSISTENTLY ---
                st.session_state['agent_memory'].update({
                    "carbon_metrics": {"co2": est_co2, "score": sust_score, "source": analysis_mode},
                    "carbon_report": clean_report
                })

        # --- DISPLAY FROM MEMORY (Not just local variables) ---
        # This ensures it persists when you chat!
        metrics = st.session_state['agent_memory'].get("carbon_metrics")
        report = st.session_state['agent_memory'].get("carbon_report")

        if metrics and report:
            st.subheader(f"📊 Impact Dashboard — {metrics['source']}")
            m1, m2, m3 = st.columns(3)
            m1.metric("Est. Carbon Emissions", f"{metrics['co2']:.2f} kg CO2e")
            m2.metric("Equivalent Car Travel", f"{metrics['co2'] * 4:.1f} km")
            m3.metric("Trees Needed to Offset", f"{metrics['co2'] / 20:.1f} trees/year")
            
            st.progress(metrics['score'] / 100)
            st.caption(f"Sustainability Score: {metrics['score']}/100")
            
            st.markdown("### 📝 Scientist's Report")
            st.write(report)