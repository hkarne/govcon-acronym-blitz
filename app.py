import json
import random
from pathlib import Path
import pandas as pd
from datetime import datetime
import streamlit as st
from streamlit_gsheets import GSheetsConnection

# Set page configuration for mobile and desktop layout
st.set_page_config(page_title="GovCon Acronym Blitz", page_icon="🎓", layout="centered")

DATA_FILE = Path(__file__).resolve().parent / "data.json"
REQUIRED_CARD_KEYS = ("acronym", "correct_answer", "distractors", "explanation")

@st.cache_data
def load_data():
    if not DATA_FILE.is_file():
        raise FileNotFoundError(f"Could not find data file at {DATA_FILE}")

    with DATA_FILE.open(encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list) or not data:
        raise ValueError("data.json must be a non-empty JSON array of acronym cards.")

    for i, card in enumerate(data):
        if not isinstance(card, dict):
            raise ValueError(f"Card at index {i} must be an object.")
        missing = [key for key in REQUIRED_CARD_KEYS if key not in card]
        if missing:
            raise ValueError(f"Card at index {i} is missing keys: {', '.join(missing)}")
        if not isinstance(card["distractors"], list) or len(card["distractors"]) != 2:
            raise ValueError(f"Card at index {i} must have exactly two distractors.")

    return data


# --- GOOGLE SHEETS LEADERBOARD LOGIC ---
def load_leaderboard():
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        df = conn.read(worksheet="Sheet1", usecols=[0, 1, 2, 3])
        df = df.dropna(how="all") # Clean up empty rows
        return df.to_dict('records')
    except Exception as e:
        st.error(f"Could not connect to leaderboard: {e}")
        return []

def save_to_leaderboard(name, score, strikes):
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(worksheet="Sheet1", usecols=[0, 1, 2, 3])
    df = df.dropna(how="all")
    
    # Create the new entry
    new_data = pd.DataFrame([{
        "Name": name.upper(), 
        "Score": score, 
        "Strikes": strikes,
        "Date": datetime.now().strftime("%Y-%m-%d")
    }])
    
    # Combine old data with new data and sort it
    updated_df = pd.concat([df, new_data], ignore_index=True)
    updated_df = updated_df.sort_values(by=['Score', 'Strikes'], ascending=[False, True])
    
    # Push back to Google Sheets
    conn.update(worksheet="Sheet1", data=updated_df)
# ---------------------------------------


try:
    all_acronyms = load_data()
except (json.JSONDecodeError, OSError, ValueError, FileNotFoundError) as exc:
    st.error(f"Could not load acronym data from **data.json**: {exc}")
    st.stop()
    
TOTAL_QUESTIONS = min(25, len(all_acronyms))
MAX_STRIKES = 3

# 2. Initialize Session State (The Game's Memory)
if "game_started" not in st.session_state:
    st.session_state.game_started = False
if "game_over" not in st.session_state:
    st.session_state.game_over = False

def reset_game():
    st.session_state.game_deck = random.sample(all_acronyms, TOTAL_QUESTIONS)
    st.session_state.current_idx = 0
    st.session_state.score = 0
    st.session_state.strikes = 0
    st.session_state.selected_option = None
    st.session_state.answered = False
    st.session_state.shuffled_options = []
    st.session_state.game_started = True
    st.session_state.game_over = False
    st.session_state.score_submitted = False

# --- MAIN UI LAYOUT ---
st.title("🏛️ GovCon Acronym Blitz")

# Create Tabs for Game and Leaderboard
tab1, tab2 = st.tabs(["🎮 Play Game", "🏆 Leaderboard"])

# --- TAB 1: THE GAME ---
with tab1:
    # 3. Start Screen
    if not st.session_state.game_started:
        st.write("Master public sector terminology. Can you survive 25 rapid-fire questions before hitting 3 strikes?")
        if st.button("Start Game", type="primary", use_container_width=True):
            reset_game()
            st.rerun()

    # 4. Active Gameplay
    else:
        idx = st.session_state.current_idx
        score = st.session_state.score
        strikes = st.session_state.strikes

        # Check Game Over Conditions
        if strikes >= MAX_STRIKES or idx >= TOTAL_QUESTIONS:
            st.session_state.game_over = True
            
            if strikes >= MAX_STRIKES:
                st.error("🚨 GAME OVER! You hit 3 strikes.")
            else:
                st.balloons()
                st.success("🏆 VICTORY! You cleared the gauntlet! Your reward is... a 500-page RFP you have to read by Monday.")
            
            st.metric(label="Final Score", value=f"{score} / {TOTAL_QUESTIONS}")
            
            # --- Score Submission UI ---
            st.write("---")
            if not st.session_state.score_submitted:
                st.markdown("### Enter the Leaderboard")
                player_name = st.text_input("Enter your initials (max 3 letters):", max_chars=3)
                if st.button("Submit Score", type="primary"):
                    if player_name:
                        save_to_leaderboard(player_name, score, strikes)
                        st.session_state.score_submitted = True
                        st.success("Score saved! Check the Leaderboard tab.")
                        st.rerun()
                    else:
                        st.warning("Please enter your initials to save your score.")
            else:
                st.info("Score successfully submitted!")

            if st.button("Play Again", type="primary", use_container_width=True):
                reset_game()
                st.rerun()
            
        # Active Question Loop
        if not st.session_state.game_over:
            current_card = st.session_state.game_deck[idx]
            
            # Generate and shuffle options ONLY ONCE per new question
            if not st.session_state.answered and not st.session_state.shuffled_options:
                opts = [current_card["correct_answer"]] + current_card["distractors"]
                random.shuffle(opts)
                st.session_state.shuffled_options = opts

            # Scoreboard UI
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Question:** {idx + 1} of {TOTAL_QUESTIONS}")
            with col2:
                heart_display = "❤️ " * (MAX_STRIKES - strikes) + "🖤 " * strikes
                st.markdown(f"**Lives:** {heart_display} | **Score:** {score}")

            st.progress((idx) / TOTAL_QUESTIONS)
            st.write("---")

            # Display Prompt
            st.markdown(f"<h1 style='text-align: center; color: #1E3A8A;'>{current_card['acronym']}</h1>", unsafe_allow_html=True)
            st.write("What does this acronym stand for?")

            # Handle Answer Buttons
            for option in st.session_state.shuffled_options:
                if not st.session_state.answered:
                    # Clickable active options
                    if st.button(option, use_container_width=True):
                        st.session_state.selected_option = option
                        st.session_state.answered = True
                        if option == current_card["correct_answer"]:
                            st.session_state.score += 1
                        else:
                            st.session_state.strikes += 1
                        st.rerun()
                else:
                    # Static colored feedback buttons after click
                    if option == current_card["correct_answer"]:
                        st.button(f"✅ {option}", disabled=True, use_container_width=True)
                    elif option == st.session_state.selected_option and option != current_card["correct_answer"]:
                        st.button(f"❌ {option}", disabled=True, use_container_width=True)
                    else:
                        st.button(option, disabled=True, use_container_width=True)

            # 5. Pause-and-Learn Context Section
            if st.session_state.answered:
                st.write("---")
                if st.session_state.selected_option == current_card["correct_answer"]:
                    st.success("**Correct**")
                else:
                    st.error(f"**Incorrect**\n\n {current_card['correct_answer']} ")
                
                # Displays just the one-line explanation with no extra labels
                st.info(current_card['explanation']) 

                # Advance Button
                if st.button("Next ➡️", type="primary", use_container_width=True):
                    st.session_state.current_idx += 1
                    st.session_state.answered = False
                    st.session_state.selected_option = None
                    st.session_state.shuffled_options = []
                    st.rerun()

# --- TAB 2: LEADERBOARD ---
with tab2:
    st.markdown("### Top Contractors")
    board_data = load_leaderboard()
    
    if len(board_data) == 0:
        st.write("No scores yet. Be the first to clear the gauntlet!")
    else:
        # Display top 10 scores using Streamlit's native dataframe UI
        st.dataframe(
            board_data[:10], 
            use_container_width=True,
            hide_index=True
        )