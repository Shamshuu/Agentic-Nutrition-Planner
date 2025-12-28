# 🥗 Agentic Nutrition Planner  
**AI-Powered Personalized Meal Planning & Sustainability Analysis System**

---

## 📌 Project Overview

**Agentic Nutrition Planner** is an intelligent, multi-agent web application that generates **personalized diet plans** based on a user’s health profile, fitness goals, budget constraints, dietary preferences, and sustainability considerations.

Unlike static meal-planning tools, this system uses **multiple collaborating AI agents** to reason, plan, adapt, and refine nutrition strategies dynamically.

---

## 🎯 Problem Definition and Design

### 🔍 Problem Definition

Most existing nutrition and fitness applications rely on **static meal templates** and manual user-driven adjustments. These systems struggle to handle:
- Changing user constraints (budget, food availability, preferences)
- Repeated plan rejections or partial compliance
- Lack of explainability behind recommendations
- No consideration of environmental sustainability

As a result, users often abandon plans due to poor adaptability and low trust.

### 👥 Target Users and Use Cases

**Target Users**:
- Students managing nutrition on limited budgets
- Fitness-focused individuals aiming for weight gain or weight loss
- Health-conscious users seeking sustainable food choices

**Primary Use Cases**:
- Generate personalized meal plans based on health goals
- Adapt plans dynamically using user feedback
- Track actual food intake via images
- Evaluate carbon footprint of food choices
- Maintain long-term dietary memory and insights

### 🤖 Why an Agentic System?

A traditional rule-based or single-model system is insufficient for this problem because nutrition planning requires:
- Multi-step reasoning (health → food → cost → sustainability)
- Continuous adaptation based on feedback and behavior
- Context-aware decision-making over time

An **agentic system** is justified because it allows:
- Autonomous reasoning across multiple specialized agents
- Explicit goal management (health, budget, sustainability)
- Separation of concerns with explainable decisions
- Planned autonomy for future self-initiated actions

---

## 🧠 High-Level System Architecture and Workflow

```
User Interaction (UI / Chat / Buttons)
        ↓
Intent Detection Agent
        ↓
Request Analysis Agent
        ↓
Doctor Agent (Nutrition Targets)
        ↓
Chef Agent (Meal Design)
        ↓
Budget Agent (Cost Optimization)
        ↓
Manager Agent (Formatting & Validation)
        ↓
Environmental Analyst (CO₂ & Sustainability)
        ↓
Optional Action Triggers
  ├─ Recipe Agent (web search & instructions)
  └─ Ordering Agent (grocery platforms)
        ↓
Persistent Memory (SQLite + Session State)
```

**Workflow Summary**:
1. User provides goals or feedback
2. Intent is detected dynamically
3. Constraints are extracted and analyzed
4. Specialized agents collaborate to generate a plan
5. Plan is validated, formatted, and presented
6. User can approve, refine, or trigger external actions
7. Approved plans and behaviors are stored as long-term memory

---

## 🤖 Agent Roles, Goals, and Constraints

Each agent operates with a **clearly defined role, goal, and set of constraints**, enabling coordinated decision-making.

| Agent | Goal | Key Constraints |
|------|------|----------------|
| Intent Detection Agent | Correctly infer user intent | Must return structured JSON, no hallucination |
| Request Analysis Agent | Extract constraints from user feedback | Preserve budget, dislikes, preferences |
| Doctor Agent | Ensure safe calorie & protein targets | Avoid unhealthy calorie deficits |
| Chef Agent | Design complete, varied meals | Respect diet type, allergies, preferences |
| Budget Agent | Optimize grocery list cost | Stay within budget targets |
| Manager Agent | Produce readable, structured output | No loss of critical information |
| Environmental Analyst | Estimate sustainability impact | Use conservative LCA assumptions |
| Recipe Agent (planned) | Provide cooking instructions | Use reliable web sources |
| Ordering Agent (planned) | Place grocery orders | Availability & platform constraints |

------|---------------|
| Intent Detection Agent | Detects whether the user wants a new plan, refinement, or a general question |
| Request Analysis Agent | Extracts constraints like budget, dislikes, preferences |
| Doctor Agent | Computes and validates calorie & protein targets |
| Chef Agent | Designs complete, varied meals |
| Budget Agent | Calculates grocery list and total cost |
| Manager Agent | Formats the final plan for readability |
| Environmental Analyst | Estimates CO₂ footprint and sustainability score |
| Recipe Agent (planned) | Retrieves cooking instructions from the web |
| Ordering Agent (planned) | Places grocery orders automatically |

---

## ✨ Features Implemented

### ✅ User Authentication
- Secure signup and login
- Password hashing (SHA-256)
- Persistent profiles using SQLite

### ✅ Strategic Meal Planner
- 1–7 day meal plans
- Weight gain / loss / maintenance goals
- Meals-per-day customization
- Budget-aware grocery planning
- Calorie & protein targeting

### ✅ Feedback-Driven Refinement
- Reject any plan with feedback
- AI regenerates plan based on constraints
- Supports budget increase / decrease

### ✅ Visual Food Tracker
- Upload food images
- AI identifies meals and estimates nutrition
- Food diary stored in agent memory

### ✅ Sustainability & Carbon Footprint
- CO₂ estimation based on meal composition
- Sustainability score (0–100)
- Green food swap suggestions

### ✅ Long-Term Memory
- Stores approved diet plans
- Uses previous plans as conversational context
- Tracks food diary and carbon metrics

---

## 🛠️ Tech Stack

|     Layer     |      Technology     |
|---------------|---------------------|
|   Frontend    |      Streamlit      |
| LLM Inference | Groq (LLaMA-3.1-8B) |
|  Vision Model |    Google Gemini    |
|    Database   |        SQLite       |
|    Language   |    Python 3.10+     |

---

## 📁 Project Structure

```
app_old.py          # Main Streamlit application
nutrition_memory.db # Auto-generated SQLite database
.env                # API keys
requirements.txt
README.md
```

---

## 📦 Dependencies

### requirements.txt

```
streamlit
groq
google-genai
pillow
python-dotenv
```

> ⚠️ Standard library modules such as `hashlib`, `sqlite3`, `re`, `datetime`, and `os` are included with Python and must not be listed as dependencies.

---

## 🔑 Environment Setup

Create a `.env` file in the project root:

```
GROQ_API_KEY=your_groq_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
```

---

## ▶️ Execution Process

1. **Create a virtual environment (recommended)**
   ```bash
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**
   ```bash
   streamlit run app.py
   ```

The application will launch automatically in the browser.

---

## 🧪 How to Use the Application

1. Sign up or log in
2. Complete your health profile
3. Generate a meal plan (1–7 days)
4. Approve, refine, or regenerate the plan
5. Upload meal photos for visual tracking
6. Analyze sustainability and carbon impact
7. Chat with the AI assistant for guidance

---

## 🚀 Future Enhancements (Planned Agent Capabilities)

### 🍳 Recipe Agent
- Triggered when the user clicks **“View Recipe”** on any meal
- Searches the web for authentic cooking instructions
- Returns:
  - Step-by-step cooking process
  - Estimated cooking time
  - Required utensils
  - Health-focused cooking tips

### 🛒 Ordering Agent
- Triggered when the user clicks **“Approve & Order”**
- Automatically converts the grocery list into an order
- Integrates with platforms such as:
  - Zepto
  - Swiggy Instamart
  - BigBasket
- Handles substitutions if items are unavailable

### 🤖 Autonomous Review Agent
- Periodically evaluates planned vs actual intake
- Detects budget or calorie deviations
- Initiates corrective actions without user prompts

### 🧠 Learning & Adaptation Layer
- Learns user preferences over time
- Identifies frequently rejected foods
- Improves future recommendations automatically

### 🔍 Self-Critic / Auditor Agent
- Verifies macro calculations
- Validates budget accuracy
- Ensures safety and constraint compliance

---

## 🏁 Conclusion

This project demonstrates a **true agentic AI system** for healthcare and fitness by combining:
- Multi-agent reasoning
- Persistent memory
- Constraint-aware planning
- Human-in-the-loop refinement
- Planned autonomy and real-world actions