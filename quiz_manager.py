# quiz_manager.py
import os
from supabase import create_client, Client

# --- Database Connection ---
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = None
if url and key:
    try:
        supabase = create_client(url, key)
        print("✅ Successfully connected to Supabase.")
    except Exception as e:
        print(f"❌ CRITICAL: Failed to create Supabase client: {e}")
else:
    print("⚠️ WARNING: SUPABASE_URL or SUPABASE_KEY not found.")

# This is our in-memory storage (the cache)
QUIZ_CACHE = {}

def get_quiz_set(set_id: str):
    """
    "Smart" function: first checks cache, then falls back to Supabase.
    """
    # 1. Check the cache first
    if set_id in QUIZ_CACHE and 'questions' in QUIZ_CACHE[set_id]:
        print(f"✅ Found '{set_id}' with questions in cache.")
        return QUIZ_CACHE[set_id]

    # 2. If not in cache or incomplete, search in Supabase
    if not supabase:
        return None

    print(f"🟡 '{set_id}' not in cache. Searching in Supabase...")
    try:
        # *** THE FIX IS HERE: We now fetch 'name' AND 'questions' ***
        response = supabase.table('quizzes').select('name', 'questions').eq('set_id', set_id).single().execute()
        
        if response.data:
            print(f"👍 Found '{set_id}' in Supabase. Caching it.")
            # 3. Store the complete data in the cache
            QUIZ_CACHE[set_id] = response.data
            return response.data
        else:
            print(f"❌ '{set_id}' not found in Supabase.")
            return None
    except Exception as e:
        print(f"Error fetching from Supabase: {e}")
        return None

def get_all_sets():
    """
    This function gets the list of all quizzes for the start menu.
    """
    if not supabase:
        return {}
        
    try:
        response = supabase.table('quizzes').select('set_id', 'name').execute()
        if response.data:
            all_sets = {item['set_id']: {'name': item['name']} for item in response.data}
            # Also, update our cache with the names
            for set_id, data in all_sets.items():
                if set_id not in QUIZ_CACHE:
                    QUIZ_CACHE[set_id] = {}
                QUIZ_CACHE[set_id]['name'] = data['name']
            return all_sets
        return {}
    except Exception as e:
        print(f"Error fetching all sets from Supabase: {e}")
        return {}
