# quiz_manager.py

"""
This module acts as the central library for all quiz data.
Its only job is to store and provide quiz sets.
"""

QUIZ_SETS = {
    "set_1_general_knowledge": {
        "name": "General Knowledge 🧠",
        "questions": [
            {"id": "q1", "question": "भारत की राजधानी क्या है?", "options": ["मुंबई", "नई दिल्ली", "चेन्नई", "कोलकाता"], "correct_option_id": 1},
            {"id": "q2", "question": "Python में लिस्ट बनाने के लिए किस ब्रैकेट का उपयोग किया जाता है?", "options": ["{}", "()", "[]", "<>"], "correct_option_id": 2},
            {"id": "q3", "question": "सूर्य किस दिशा में उगता है?", "options": ["पश्चिम", "उत्तर", "पूर्व", "दक्षिण"], "correct_option_id": 2},
            {"id": "q4", "question": "1 KB में कितने बाइट्स होते हैं?", "options": ["1000", "1024", "2048", "512"], "correct_option_id": 1},
            {"id": "q5", "question": "इनमें से कौन सा एक सर्च इंजन नहीं है?", "options": ["Google", "Yahoo", "Instagram", "Bing"], "correct_option_id": 2}
        ]
    },
    "set_2_science": {
        "name": "Science Challenge 🧪",
        "questions": [
            {"id": "s1", "question": "What is the chemical formula for water?", "options": ["O2", "H2O", "CO2", "NaCl"], "correct_option_id": 1},
            {"id": "s2", "question": "How many bones are in the human body?", "options": ["206", "300", "150", "256"], "correct_option_id": 0},
        ]
    }
    # Future quizzes can be added here
    # "set_3_movies": { ... }
}

def get_quiz_set(set_id: str):
    """Returns the quiz data (name and questions) for a given set_id."""
    return QUIZ_SETS.get(set_id)

def get_all_sets():
    """Returns the entire dictionary of quiz sets to build the start menu."""
    return QUIZ_SETS
