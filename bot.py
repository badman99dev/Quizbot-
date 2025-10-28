import asyncio
import logging
import os
import random
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, PollHandler, PollAnswerHandler, ContextTypes

# --- Configuration ---
QUIZ_NAME = "Advanced Test"
QUESTIONS_PER_QUIZ = 5
SECONDS_PER_QUESTION = 15

# --- Scoring Configuration ---
POINTS_CORRECT = 100
POINTS_WRONG_PENALTY = -25
MAX_SPEED_BONUS = 50

# --- Dummy Questions ---
dummy_questions = [
    {"id": "q1", "question": "भारत की राजधानी क्या है?", "options": ["मुंबई", "नई दिल्ली", "चेन्नई", "कोलकाता"], "correct_option_id": 1},
    {"id": "q2", "question": "Python में लिस्ट बनाने के लिए किस ब्रैकेट का उपयोग किया जाता है?", "options": ["{}", "()", "[]", "<>"], "correct_option_id": 2},
    {"id": "q3", "question": "सूर्य किस दिशा में उगता है?", "options": ["पश्चिम", "उत्तर", "पूर्व", "दक्षिण"], "correct_option_id": 2},
    {"id": "q4", "question": "1 KB में कितने बाइट्स होते हैं?", "options": ["1000", "1024", "2048", "512"], "correct_option_id": 1},
    {"id": "q5", "question": "इनमें से कौन सा एक सर्च इंजन नहीं है?", "options": ["Google", "Yahoo", "Instagram", "Bing"], "correct_option_id": 2}
]

# --- Bot Logic ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Helper Functions ---
def get_question_by_id(qid):
    return next((q for q in dummy_questions if q["id"] == qid), None)

def calculate_points(time_taken):
    if time_taken < 2: return MAX_SPEED_BONUS
    if time_taken >= SECONDS_PER_QUESTION: return 0
    bonus = MAX_SPEED_BONUS * (1 - (time_taken / SECONDS_PER_QUESTION))
    return int(bonus)

# --- Core Bot Functions ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    keyboard = [[InlineKeyboardButton("✅ I'm ready!", callback_data='start_quiz')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"🎲 Welcome to the '{QUIZ_NAME}'!\n\n"
        f"This quiz features an advanced scoring system:\n"
        f"• **Correct:** `{POINTS_CORRECT}` pts\n"
        f"• **Wrong:** `{POINTS_WRONG_PENALTY}` pts\n"
        f"• **Speed Bonus:** Up to `{MAX_SPEED_BONUS}` pts\n\n"
        f"Press the button when you are ready to start!",
        reply_markup=reply_markup, parse_mode='Markdown'
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = update.effective_chat.id
    user_data = context.user_data

    if data == 'start_quiz':
        await query.edit_message_text(text="🚀 Getting the quiz ready...")
        shuffled_questions = random.sample(dummy_questions, k=QUESTIONS_PER_QUIZ)
        user_data.update({
            'questions_queue': [q['id'] for q in shuffled_questions], 'questions_answered': 0,
            'total_score': 0, 'correct_answers': 0, 'wrong_answers': 0,
            'quiz_start_time': time.time(), 'active_poll_message_id': None, 'active_poll_id': None
        })
        await start_countdown_and_quiz(chat_id, context)
    
    elif data in ['postpone_question', 'skip_permanently', 'stop_quiz']:
        active_poll_id = user_data.get('active_poll_id')
        if active_poll_id in context.bot_data:
            # Manually trigger the timeout logic for the current poll
            quiz_info = context.bot_data.pop(active_poll_id) # Important: pop it
            if data == 'postpone_question': quiz_info['postponed'] = True
            elif data == 'skip_permanently': quiz_info['skipped'] = True
            elif data == 'stop_quiz': quiz_info['stopped'] = True
            
            await handle_poll_closure(chat_id, context, quiz_info)

    elif data == 'try_again':
        await query.message.delete()
        await start_command(update.effective_message, context)


async def start_countdown_and_quiz(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = await context.bot.send_message(chat_id, text="Get Ready... 3️⃣")
    await asyncio.sleep(1); await msg.edit_text("Get Ready... 2️⃣")
    await asyncio.sleep(1); await msg.edit_text("Get Ready... 1️⃣")
    await asyncio.sleep(1); await msg.edit_text("🚦 GO!")
    await asyncio.sleep(0.5); await msg.delete()
    await send_next_question(chat_id, context)

async def send_next_question(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_data = context.user_data
    
    if user_data.get('active_poll_message_id'):
        try:
            await context.bot.delete_message(chat_id, user_data['active_poll_message_id'])
        except BadRequest: pass # Ignore if message not found
        user_data['active_poll_message_id'] = None

    if not user_data.get('questions_queue'):
        await show_final_score(chat_id, context)
        return

    question_id = user_data['questions_queue'][0]
    question_data = get_question_by_id(question_id)
    
    current_q_num = user_data.get('questions_answered', 0) + 1

    is_postponed = user_data.get(f"is_postponed_{question_id}", False)
    
    keyboard = [[InlineKeyboardButton("⏹️ Stop Quiz", callback_data='stop_quiz')]]
    if is_postponed:
        keyboard[0].append(InlineKeyboardButton("⏩ Skip Permanently", callback_data='skip_permanently'))
    else:
        keyboard[0].append(InlineKeyboardButton("➡️ Postpone", callback_data='postpone_question'))

    message = await context.bot.send_poll(
        chat_id=chat_id, question=f"Q {current_q_num}/{QUESTIONS_PER_QUIZ}: {question_data['question']}",
        options=question_data["options"], type='quiz', correct_option_id=question_data["correct_option_id"],
        open_period=SECONDS_PER_QUESTION, is_anonymous=False, reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    user_data['active_poll_message_id'] = message.message_id
    user_data['active_poll_id'] = message.poll.id
    context.bot_data[message.poll.id] = {
        "chat_id": chat_id, "correct_option_id": question_data["correct_option_id"],
        "question_id": question_id, "time_sent": time.time()
    }

async def poll_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    answer = update.poll_answer
    poll_id = answer.poll_id

    if poll_id in context.bot_data:
        quiz_info = context.bot_data.pop(poll_id)
        user_data = context.user_data
        
        # ** THE FIX IS HERE **
        # We get chat_id from our stored quiz_info, not from the update object
        chat_id = quiz_info["chat_id"]
        
        user_data['questions_queue'].pop(0)
        user_data['questions_answered'] += 1
        
        time_taken = time.time() - quiz_info['time_sent']
        is_correct = answer.option_ids[0] == quiz_info["correct_option_id"]
        
        points = 0
        if is_correct:
            user_data['correct_answers'] += 1
            speed_bonus = calculate_points(time_taken)
            points = POINTS_CORRECT + speed_bonus
            await context.bot.send_message(chat_id, f"✅ Correct! +{points} pts (+{speed_bonus} bonus)")
        else:
            user_data['wrong_answers'] += 1
            points = POINTS_WRONG_PENALTY
            await context.bot.send_message(chat_id, f"❌ Wrong! {points} pts")
        
        user_data['total_score'] += points
        await asyncio.sleep(2)
        await send_next_question(chat_id, context)

async def poll_timeout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    poll_id = update.poll.id
    if poll_id in context.bot_data and update.poll.is_closed:
        quiz_info = context.bot_data.pop(poll_id)
        chat_id = quiz_info["chat_id"]
        await handle_poll_closure(chat_id, context, quiz_info)

async def handle_poll_closure(chat_id, context, quiz_info):
    """A new central function to handle any poll that closes, for any reason."""
    user_data = context.user_data
    question_id = user_data['questions_queue'].pop(0)

    if quiz_info.get('postponed'):
        user_data['questions_queue'].append(question_id)
        user_data[f"is_postponed_{question_id}"] = True
        await context.bot.send_message(chat_id, "Question postponed to the end.")
    elif quiz_info.get('skipped'):
        user_data['questions_answered'] += 1
        await context.bot.send_message(chat_id, "Question skipped permanently.")
    elif quiz_info.get('stopped'):
        return # Stop command shows the score, so we do nothing here
    else: # Regular timeout
        user_data['questions_answered'] += 1
        await context.bot.send_message(chat_id, "⌛️ Time's up! No points awarded.")

    await asyncio.sleep(1.5)
    await send_next_question(chat_id, context)

async def show_final_score(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_data = context.user_data
    total_score = user_data.get('total_score', 0)
    correct = user_data.get('correct_answers', 0)
    answered = user_data.get('questions_answered', 0)
    
    accuracy_bonus = 0; accuracy = 0
    if answered > 0:
        accuracy = (correct / answered) * 100
        accuracy_bonus = int(total_score * (accuracy / 100) * 0.1) if total_score > 0 else 0
    
    final_score = total_score + accuracy_bonus
    
    score_text = (
        f"🏁 **Quiz Over!** 🏆\n\n"
        f"Base Score: `{total_score}`\n"
        f"Accuracy: `{accuracy:.1f}%` (+`{accuracy_bonus}` bonus)\n"
        f"**Final Score: `{final_score}`**\n\n"
        f"Correct: `{correct}` | Wrong/Missed: `{answered - correct}`"
    )
    keyboard = [[InlineKeyboardButton("🔄 Try Again", callback_data='try_again')]]
    await context.bot.send_message(
        chat_id, text=score_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
    )
    user_data.clear()

def main() -> None:
    TOKEN = os.getenv("TELEGRAM_TOKEN")
    if not TOKEN: raise ValueError("TELEGRAM_TOKEN not set!")
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(PollAnswerHandler(poll_answer_handler))
    application.add_handler(PollHandler(poll_timeout_handler))
    application.run_polling()

if __name__ == '__main__':
    main()
