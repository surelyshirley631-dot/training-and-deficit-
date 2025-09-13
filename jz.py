# yyxapp.py
# Streamlit app implementing your spec:
# 1) user info -> BMR (Mifflin-St Jeor)
# 2) compute b = a / 0.7
# 3) add cardio d and optional strength training c
# 4) target calories for fat loss: f = e * 0.64
# 5) fixed fat grams (male 60 or 70 if >=120kg, female 50)
# 6) macro distribution & per-meal splits and food suggestions from uploaded DB
#
# Requirements: streamlit, pandas
# Run: streamlit run yyxapp.py

import streamlit as st
import pandas as pd
import math
from typing import List

st.set_page_config(page_title="Calorie & Meal Planner", layout="wide")

st.title("Calorie & Meal Planner — Fat Loss Mode (your spec)")

# -----------------------
# Helper functions
# -----------------------
def calc_bmr_mifflin(weight, height_cm, age, sex):
    # weight kg, height cm
    if sex.lower() in ("male", "m"):
        return weight * 9.99 + height_cm * 6.25 - age * 4.92 + 5
    else:
        return weight * 9.99 + height_cm * 6.25 - age * 4.92 - 161

def grams_to_cal_fat(g):
    return g * 9

def kcal_to_grams_protein(kcal):
    return kcal / 4

def kcal_to_grams_carb(kcal):
    return kcal / 4

def safe_div(a,b):
    return a/b if b else 0

# Simple food selection helpers
def load_food_db(df):
    # Expect columns: food, category (carb/protein/fat/veg/fruit/other), cal_per_100g, protein_g_per_100g, carbs_g_per_100g, fat_g_per_100g, tags (semicolon)
    # We'll be tolerant to column presence
    if df is None:
        return None
    cols = [c.lower() for c in df.columns]
    required = 'food' in cols and 'cal_per_100g' in cols
    if not required:
        return None
    # normalize column names to lowercase keys
    df.columns = [c.lower() for c in df.columns]
    # ensure category column exists
    if 'category' not in df.columns:
        # try to infer category from tags
        if 'tags' in df.columns:
            def infer_cat(tags):
                t = str(tags).lower()
                if 'protein' in t or 'meat' in t or 'fish' in t or 'egg' in t: return 'protein'
                if 'grain' in t or 'carb' in t or 'rice' in t or 'oat' in t or 'bread' in t or 'potato' in t or 'sweet' in t: return 'carb'
                if 'vegetable' in t or 'veg' in t or 'broccoli' in t or 'spinach' in t: return 'veg'
                if 'fruit' in t or 'banana' in t or 'apple' in t: return 'fruit'
                if 'fat' in t or 'oil' in t or 'olive' in t or 'almond' in t or 'nut' in t: return 'fat'
                return 'other'
            df['category'] = df.get('tags', '').apply(infer_cat)
        else:
            df['category'] = 'other'
    return df

def sample_foods(df, category, n=2):
    if df is None:
        return []
    subset = df[df['category'] == category]
    if subset.empty:
        # fallback: try tags-based search
        if 'tags' in df.columns:
            subset = df[df['tags'].str.contains(category, case=False, na=False)]
    if subset.empty:
        return []
    return subset.sample(min(n, len(subset))).to_dict('records')

# -----------------------
# Left column: Inputs
# -----------------------
with st.sidebar:
    st.header("User info & settings")
    name = st.text_input("Name")
    sex = st.selectbox("Sex", ["Male", "Female"])
    age = st.number_input("Age", min_value=13, max_value=100, value=28)
    height_cm = st.number_input("Height (cm)", min_value=120, max_value=220, value=165)
    weight_kg = st.number_input("Weight (kg)", min_value=30.0, max_value=200.0, value=60.0, format="%.1f")
    bmi_manual = st.checkbox("I will input BMI manually (otherwise computed)")
    if bmi_manual:
        bmi = st.number_input("BMI", min_value=10.0, max_value=60.0, value=round(weight_kg / ((height_cm/100)**2),1))
    else:
        bmi = round(weight_kg / ((height_cm/100)**2), 1)
    st.markdown(f"**Calculated BMI:** {bmi}")

    st.markdown("---")
    st.header("Activity & Goal")
    has_strength = st.radio("Do you have regular strength training?", ("No", "Yes"))
    if has_strength == "Yes":
        strength_level = st.selectbox("Strength level (affects est kcal burned)", ["Beginner", "Intermediate", "Advanced"])
        strength_est_map = {"Beginner": 150, "Intermediate": 200, "Advanced": 250}
        strength_cal = strength_est_map[strength_level]
    else:
        strength_cal = 0

    cardio_cal = st.number_input("Average cardio kcal/day (enter 0 if none, if you do weekly cardio, divide by 7)", min_value=0, value=0)

    st.markdown("---")
    st.header("Goal")
    goal = st.selectbox("Goal", ["Fat Loss"], index=0)  # you asked for fat loss mode
    # In future we can support gain muscle with different multipliers

    st.markdown("---")
    st.header("Upload food DB (optional)")
    uploaded_file = st.file_uploader("Upload CSV with columns: food, category, cal_per_100g, protein_g_per_100g, carbs_g_per_100g, fat_g_per_100g, tags", type=["csv"])
    db_df = None
    if uploaded_file is not None:
        try:
            db_df = pd.read_csv(uploaded_file)
            db_df = load_food_db(db_df)
            if db_df is None:
                st.warning("Uploaded CSV missing expected columns; app will use sample suggestions.")
            else:
                st.success("Food DB loaded.")
        except Exception as e:
            st.error("Failed to read CSV: " + str(e))
            db_df = None

# -----------------------
# Main calculation
# -----------------------
st.header("Calculation results")

# 1. BMR
bmr = calc_bmr_mifflin(weight_kg, height_cm, age, sex)
st.write(f"**BMR (a)**: {bmr:.0f} kcal (Mifflin–St Jeor)")

# 2. No-exercise total consumption b = a / 0.7
no_activity_total = bmr / 0.7
st.write(f"**No-exercise total consum. (b = a / 0.7)**: {no_activity_total:.0f} kcal")

# 3 & 4 & 5: handle training/no training cases and compute e/f
st.subheader("Calorie scenarios (Fat loss)")

if has_strength == "No":
    # 5.1 No strength training
    e = no_activity_total + cardio_cal  # balance calories
    f = e * 0.64
    st.write("**No strength training (only optional cardio)**")
    st.write(f"- Balance calories (e = b + d): {e:.0f} kcal")
    st.write(f"- Target intake (f = e × 0.64): {f:.0f} kcal")
    # We will use f as the daily target for meal breakdown
    daily_target_train = f
    daily_target_rest = f
else:
    # 5.2 Has strength training
    c = strength_cal
    d = cardio_cal
    e1 = no_activity_total + c + d
    f1 = e1 * 0.64
    e2 = no_activity_total + d
    f2 = e2 * 0.64
    st.write("**With strength training**")
    st.write(f"- Training day balance (e1 = b + c + d): {e1:.0f} kcal")
    st.write(f"- Training day target (f1 = e1 × 0.64): {f1:.0f} kcal")
    st.write(f"- Rest day balance (e2 = b + d): {e2:.0f} kcal")
    st.write(f"- Rest day target (f2 = e2 × 0.64): {f2:.0f} kcal")
    daily_target_train = f1
    daily_target_rest = f2

# Show choice: which day to display meal plan for
st.markdown("---")
day_choice = st.selectbox("Which day's meal plan to generate?", ("Training day", "Rest day"))
daily_target = daily_target_train if day_choice == "Training day" else daily_target_rest
st.metric("Selected Daily Target (kcal)", f"{daily_target:.0f} kcal")

# -----------------------
# Macronutrients
# -----------------------
st.subheader("Macronutrient targets")

# 6. Fat fixed grams logic
if sex == "Male":
    fat_grams = 70 if weight_kg >= 120 else 60
else:
    fat_grams = 50
fat_kcal = grams_to_cal_fat(fat_grams)

st.write(f"- Fixed fat intake: **{fat_grams} g** → **{fat_kcal:.0f} kcal**")

# Protein suggestion: 1.6 - 2.0 g/kg (we'll pick 1.8 g/kg as default, show range)
protein_g_per_kg = 1.8
protein_grams = round(protein_g_per_kg * weight_kg, 1)
protein_kcal = protein_grams * 4
st.write(f"- Suggested protein: **{protein_g_per_kg} g/kg** → **{protein_grams} g** → **{protein_kcal:.0f} kcal**")
st.write("  (suggested range: 1.6–2.0 g/kg; adjust if older/very lean/very heavy)")

# Remaining calories go to carbs (since fat fixed and protein chosen)
remaining_kcal = daily_target - fat_kcal - protein_kcal
if remaining_kcal < 0:
    st.error("Warning: fixed fat + suggested protein exceed daily target. Reduce protein/fat or increase calories.")
    remaining_kcal = max(0, remaining_kcal)  # avoid negative further

carb_grams = round(remaining_kcal / 4, 1)
st.write(f"- Allocated to carbs: **{carb_grams} g** → **{remaining_kcal:.0f} kcal**")

# Show ratio suggestion (as percent of total kcal)
def pct(x): return 0 if daily_target==0 else (x/daily_target*100)
st.write(f"**Macro % of daily target (approx)**: Protein {pct(protein_kcal):.0f}% | Carbs {pct(remaining_kcal):.0f}% | Fat {pct(fat_kcal):.0f}%")

st.markdown("---")

# -----------------------
# Meal distribution per your specified percentages
# Carbs: breakfast 20% / post-workout 40% / dinner 30% / snack 10%
# Protein: breakfast 20% / lunch 30% / dinner 30% / snack 20%
# We'll interpret "post-workout" as the largest carb meal (map to lunch/dinner depending on user choice)
# -----------------------
st.subheader("Meal allocation")

# Provide an input to choose training timing (8 situations) — this is used to map "post-workout" meal
train_timing = st.selectbox("Training timing (choose the one that matches you)", [
    "Train after breakfast (early wake)", "Train after breakfast (late wake)", "Train before lunch",
    "Train after lunch", "Train before dinner", "Train after dinner", "Train late night", "Rest day"
])

# Determine which meal is "post-workout"
# mapping: choose meal names Breakfast, Lunch, Dinner, Snack
if "breakfast" in train_timing.lower() and "after" in train_timing.lower():
    post_workout_meal = "Breakfast"  # in your spec, breakfast is pre, but if train after breakfast the post largest may be after training (edge case)
elif "before lunch" in train_timing.lower() or "after lunch" in train_timing.lower():
    post_workout_meal = "Lunch"
elif "before dinner" in train_timing.lower() or "after dinner" in train_timing.lower():
    post_workout_meal = "Dinner"
elif "late night" in train_timing.lower():
    post_workout_meal = "Dinner"
else:
    post_workout_meal = "Lunch"

# Carb splits (we will map post-workout 40%)
carb_splits = {
    "Breakfast": 0.20,
    "PostWorkout": 0.40,
    "Dinner": 0.30,
    "Snack": 0.10
}
# Protein splits nominal:
protein_splits = {
    "Breakfast": 0.20,
    "Lunch": 0.30,
    "Dinner": 0.30,
    "Snack": 0.20
}

# Convert carb splits into actual meal mapping: we want numeric for Breakfast, Lunch, Dinner, Snack
carb_by_meal = {"Breakfast": 0, "Lunch": 0, "Dinner": 0, "Snack": carb_splits["Snack"]}
# Assign 20% to breakfast
carb_by_meal["Breakfast"] = carb_splits["Breakfast"]
# Assign 40% to whichever meal is post-workout
if post_workout_meal in carb_by_meal:
    carb_by_meal[post_workout_meal] += carb_splits["PostWorkout"]
else:
    # default to Lunch
    carb_by_meal["Lunch"] += carb_splits["PostWorkout"]
# ensure Dinner gets its 30% (if PostWorkout also Dinner, it accumulates)
if "Dinner" not in carb_by_meal:
    carb_by_meal["Dinner"] = carb_splits["Dinner"]
else:
    carb_by_meal["Dinner"] += carb_splits["Dinner"] if carb_by_meal["Dinner"]==0 else 0

# If some meal got >1.0 from double assignment, okay — plan will show numbers
# Protein mapping is straightforward
protein_by_meal = {"Breakfast": protein_splits["Breakfast"], "Lunch": protein_splits["Lunch"], "Dinner": protein_splits["Dinner"], "Snack": protein_splits["Snack"]}

st.write("Carb % per meal (apportioned):")
st.table(pd.DataFrame({
    "meal": list(carb_by_meal.keys()),
    "carb_%": [f"{v*100:.0f}%" for v in carb_by_meal.values()],
    "carb_kcal": [daily_target * v if v else 0 for v in carb_by_meal.values()],
    "carb_g": [round(daily_target * v / 4,1) for v in carb_by_meal.values()]
}))

st.write("Protein % per meal (apportioned):")
st.table(pd.DataFrame({
    "meal": list(protein_by_meal.keys()),
    "protein_%": [f"{v*100:.0f}%" for v in protein_by_meal.values()],
    "protein_kcal": [protein_kcal * v for v in protein_by_meal.values()],
    "protein_g": [round(protein_grams * v,1) for v in protein_by_meal.values()]
}))

st.markdown("---")
st.subheader("Food suggestions (based on DB if uploaded)")

# If no db, provide default sample combos
default_carbs = [
    {"food":"Cooked white rice","cal_per_100g":130},
    {"food":"Cooked sweet potato","cal_per_100g":90},
    {"food":"Oats (dry)","cal_per_100g":389},
    {"food":"Bread (slice)","cal_per_100g":250},
]
default_proteins = [
    {"food":"Chicken breast (cooked)","cal_per_100g":165, "protein_g_per_100g":31},
    {"food":"Egg (whole)","cal_per_100g":155, "protein_g_per_100g":13},
    {"food":"Greek yogurt","cal_per_100g":59, "protein_g_per_100g":10},
    {"food":"Tofu (firm)","cal_per_100g":76, "protein_g_per_100g":8},
]

def suggest_for_meal(meal_name, carb_kcal, protein_kcal, db_df):
    # convert kcal to grams roughly using db
    suggestions = {"carbs": [], "proteins": [], "fat_notes": None}
    # carb suggestions
    if db_df is not None:
        carb_items = sample_foods(db_df, 'carb', 2)
        protein_items = sample_foods(db_df, 'protein', 2)
        # compute grams based on cal_per_100g
        for it in carb_items:
            cal100 = float(it.get('cal_per_100g', 100))
            grams = int(carb_kcal / cal100 * 100) if cal100>0 else 0
            suggestions['carbs'].append({"food": it['food'], "grams": grams, "kcal": round(cal100*grams/100)})
        for it in protein_items:
            cal100 = float(it.get('cal_per_100g', 100))
            grams = int(protein_kcal / cal100 * 100) if cal100>0 else 0
            suggestions['proteins'].append({"food": it['food'], "grams": grams, "kcal": round(cal100*grams/100)})
    else:
        # fallback from defaults
        # use first default items
        c = default_carbs[0]; p = default_proteins[0]
        grams_c = int(carb_kcal / c['cal_per_100g'] * 100) if c['cal_per_100g']>0 else 0
        grams_p = int(protein_kcal / p['cal_per_100g'] * 100) if p['cal_per_100g']>0 else 0
        suggestions['carbs'].append({"food": c['food'], "grams": grams_c, "kcal": int(c['cal_per_100g']*grams_c/100)})
        suggestions['proteins'].append({"food": p['food'], "grams": grams_p, "kcal": int(p['cal_per_100g']*grams_p/100)})
    # fat notes
    suggestions['fat_notes'] = f"Include {fat_grams} g fat across day (e.g. egg yolk, cooking oil, nuts)."
    return suggestions

# compute suggestions per meal
meals = ["Breakfast", "Lunch", "Dinner", "Snack"]
rows = []
for meal in meals:
    carb_kcal = daily_target * carb_by_meal.get(meal, 0)
    # protein_kcal per meal: use protein_kcal * fraction or compute from protein_grams fraction
    protein_kcal_meal = protein_kcal * protein_by_meal.get(meal, 0)
    sugg = suggest_for_meal(meal, carb_kcal, protein_kcal_meal, db_df)
    rows.append((meal, carb_kcal, protein_kcal_meal, sugg))

# Display suggestions
for meal, carb_kcal, protein_kcal, sugg in rows:
    st.markdown(f"### {meal}")
    st.write(f"Carb kcal: {carb_kcal:.0f} kcal → Protein kcal: {protein_kcal:.0f} kcal")
    if sugg['carbs']:
        st.write("Carb suggestion(s):")
        for it in sugg['carbs']:
            st.write(f"- {it['food']} — {it['grams']} g — {it['kcal']} kcal")
    if sugg['proteins']:
        st.write("Protein suggestion(s):")
        for it in sugg['proteins']:
            st.write(f"- {it['food']} — {it['grams']} g — {it['kcal']} kcal")
    st.write(sugg['fat_notes'])
    st.markdown("---")

# Final notes & export
st.subheader("Notes & Export")
st.write("- Vegetables: eat freely, aim for ~500 g/day. Fruits: ~300 g/day (peeled weight).")
st.write("- If you skip egg-yolk + milk breakfast, add nuts (20–30g) or extra yolks later to meet fat target.")
if st.button("Download plan as CSV"):
    # create export df
    export = []
    for meal, carb_kcal, protein_kcal, sugg in rows:
        export.append({
            "meal": meal,
            "carb_kcal": round(carb_kcal,1),
            "protein_kcal": round(protein_kcal,1),
            "carb_foods": "; ".join([f"{it['food']}({it['grams']}g)" for it in sugg['carbs']]) if sugg['carbs'] else "",
            "protein_foods": "; ".join([f"{it['food']}({it['grams']}g)" for it in sugg['proteins']]) if sugg['proteins'] else "",
            "fat_notes": sugg['fat_notes']
        })
    df_export = pd.DataFrame(export)
    csv = df_export.to_csv(index=False).encode('utf-8')
    st.download_button("Download CSV", data=csv, file_name="meal_plan.csv", mime="text/csv")

st.info("This app implements your exact spec. If you upload a food DB CSV with columns described in the sidebar, suggestions will use your data. Otherwise sample suggestions are used.")
