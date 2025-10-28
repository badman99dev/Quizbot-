# quiz_manager.py
import os
from supabase import create_client, Client

# --- Database Connection ---
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = None
if url and key:
    supabase = create_client(url, key)
else:
    print("⚠️ WARNING: SUPABASE_URL or SUPABASE_KEY not found.")

# यह हमारी मेमोरी (कैश) है, जो शुरू में खाली होगी
QUIZ_CACHE = {}

def get_quiz_set(set_id: str):
    """
    "स्मार्ट" फंक्शन: पहले कैश में खोजता है, अगर नहीं मिला तो Supabase में खोजता है।
    """
    # 1. पहले कैश में देखो
    if set_id in QUIZ_CACHE:
        print(f"✅ Found '{set_id}' in cache.")
        return QUIZ_CACHE[set_id]

    # 2. अगर कैश में नहीं मिला, तो Supabase में खोजो
    if not supabase:
        return None

    print(f"🟡 '{set_id}' not in cache. Searching in Supabase...")
    try:
        response = supabase.table('quizzes').select('name', 'questions').eq('set_id', set_id).single().execute()
        
        if response.data:
            print(f"👍 Found '{set_id}' in Supabase. Adding to cache.")
            # 3. Supabase में मिल गया, तो उसे कैश में सेव कर लो
            QUIZ_CACHE[set_id] = response.data
            return response.data
        else:
            # 4. कहीं नहीं मिला
            print(f"❌ '{set_id}' not found anywhere.")
            return None
    except Exception as e:
        print(f"Error fetching from Supabase: {e}")
        return None

def get_all_sets():
    """
    यह फंक्शन सभी क्विज की लिस्ट लाता है ताकि स्टार्ट मेनू बन सके।
    यह हमेशा Supabase से लेटेस्ट लिस्ट लाएगा।
    """
    if not supabase:
        return {}
        
    try:
        response = supabase.table('quizzes').select('set_id', 'name').execute()
        if response.data:
            # Supabase से मिली लिस्ट को सही फॉर्मेट में बदलो
            all_sets = {item['set_id']: {'name': item['name']} for item in response.data}
            # कैश को भी अपडेट कर दो
            for set_id, data in all_sets.items():
                if set_id not in QUIZ_CACHE:
                    QUIZ_CACHE[set_id] = {}
                QUIZ_CACHE[set_id]['name'] = data['name']
            return all_sets
        return {}
    except Exception as e:
        print(f"Error fetching all sets from Supabase: {e}")
        return {}
