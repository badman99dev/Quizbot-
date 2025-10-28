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
        f"🎲 Welcome to the '{QUIZ_NAME}'!\n\nPress the button when you are ready to start!",
        reply_markup=reply_markup, parse_mode='HTML'
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data.split(':')
    action = data[0]
    
    chat_id = update.effective_chat.id
    user_data = context.user_data

    if action == 'start_quiz':
        await query.edit_message_text(text="🚀 Getting the quiz ready...")
        shuffled_questions = random.sample(dummy_questions, k=QUESTIONS_PER_QUIZ)
        user_data.update({
            'questions_queue': [q['id'] for q in shuffled_questions], 'results': [],
            'total_score': 0, 'quiz_start_time': time.time(), 'active_poll_message_id': None
        })
        await start_countdown_and_quiz(chat_id, context)
    
    elif action in ['postpone_question', 'skip_permanently', 'stop_quiz']:
        active_poll_id = user_data.get('active_poll_id')
        if active_poll_id in context.bot_data:
            quiz_info = context.bot_data.pop(active_poll_id, None)
            if not quiz_info: return
            
            if action == 'postpone_question': quiz_info['postponed'] = True
            elif action == 'skip_permanently': quiz_info['skipped'] = True
            elif action == 'stop_quiz':
                await query.message.delete()
                await show_final_score(chat_id, context)
                return
            await handle_poll_closure(chat_id, context, quiz_info)

    elif action == 'try_again':
        await query.message.delete()
        await start_command(update.effective_message, context)
    
    elif action == 'detailed_review':
        await detailed_review_callback(update, context)


async def detailed_review_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    chat_id = update.effective_chat.id
    user_data = context.user_data
    results = user_data.get('results', [])

    if not results:
        await query.message.reply_text("No answers to review.")
        return

    await query.message.delete()
    
    message_chunks = []
    current_chunk = "📝 ║  <b>𝐃𝐄𝐓𝐀𝐈𝐋𝐄𝐃 𝐑𝐄𝐕𝐈𝐄𝐖</b>  ║ 📝\n\n"
    
    for i, result in enumerate(results):
        question_data = get_question_by_id(result['question_id'])
        
        options_text = ""
        for j, option in enumerate(question_data['options']):
            if j == question_data['correct_option_id']:
                options_text += f"    ✅ <code>{option}</code>\n"
            elif j == result.get('answered_option_id'):
                options_text += f"    ❌ <code>{option}</code> <i>(Your answer)</i>\n"
            else:
                options_text += f"    -  <code>{option}</code>\n"

        result_text = ""
        if result['status'] == 'correct':
            result_text = f"Status: ✅ Correct﹞﹝Points: +{result['points_earned']}﹞﹝Time: {result['time_taken']:.1f}s"
        elif result['status'] == 'wrong':
            result_text = f"Status: ❌ Wrong﹞﹝Points: {result['points_earned']}﹞﹝Time: {result['time_taken']:.1f}s"
        else:
            result_text = f"Status: ⌛ Not Answered﹞﹝Points: +0﹞﹝Time: ---"

        question_review = (
            "____________________________________\n\n"
            f"❰ <b>𝐐𝐮𝐞𝐬𝐭𝐢𝐨𝐧 {i+1}</b> ❱\n"
            f"<code>{question_data['question']}</code>\n\n"
            f"{options_text}\n"
            f"↳  <i>﹝{result_text}﹞</i>\n\n"
        )
        
        if len(current_chunk) + len(question_review) > 4000:
            message_chunks.append(current_chunk)
            current_chunk = ""
        current_chunk += question_review

    message_chunks.append(current_chunk)
    
    for chunk in message_chunks:
        await context.bot.send_message(chat_id, text=chunk, parse_mode='HTML')
        await asyncio.sleep(0.5)

    await show_final_score(chat_id, context, is_overview=True)


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
        except BadRequest: pass
        user_data['active_poll_message_id'] = None

    if not user_data.get('questions_queue'):
        await show_final_score(chat_id, context)
        return

    question_id = user_data['questions_queue'][0]
    question_data = get_question_by_id(question_id)
    
    total_answered = len(user_data.get('results', []))
    is_postponed = user_data.get(f"is_postponed_{question_id}", False)
    
    keyboard = [[InlineKeyboardButton("⏹️ Stop Quiz", callback_data='stop_quiz')]]
    if is_postponed:
        keyboard[0].append(InlineKeyboardButton("⏩ Skip Permanently", callback_data='skip_permanently'))
    else:
        keyboard[0].append(InlineKeyboardButton("➡️ Postpone", callback_data='postpone_question'))

    message = await context.bot.send_poll(
        chat_id=chat_id, question=f"Q {total_answered + 1}/{QUESTIONS_PER_QUIZ}: {question_data['question']}",
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
        chat_id = quiz_info["chat_id"]
        user_data = context.user_data
        
        user_data['questions_queue'].pop(0)
        
        time_taken = time.time() - quiz_info['time_sent']
        is_correct = answer.option_ids[0] == quiz_info["correct_option_id"]
        
        points = 0; status = ''
        if is_correct:
            status = 'correct'; speed_bonus = calculate_points(time_taken); points = POINTS_CORRECT + speed_bonus
        else:
            status = 'wrong'; points = POINTS_WRONG_PENALTY
        
        user_data['total_score'] += points
        user_data['results'].append({
            'question_id': quiz_info['question_id'], 'status': status, 'points_earned': points,
            'time_taken': time_taken, 'answered_option_id': answer.option_ids[0]
        })
        
        await send_next_question(chat_id, context)

async def poll_timeout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    poll_id = update.poll.id
    if poll_id in context.bot_data and update.poll.is_closed:
        quiz_info = context.bot_data.pop(poll_id, None)
        if not quiz_info: return
        chat_id = quiz_info["chat_id"]
        await handle_poll_closure(chat_id, context, quiz_info)

async def handle_poll_closure(chat_id, context, quiz_info):
    user_data = context.user_data
    question_id = user_data['questions_queue'].pop(0)
    
    status = 'timed_out'
    if quiz_info.get('postponed'):
        user_data['questions_queue'].append(question_id)
        user_data[f"is_postponed_{question_id}"] = True; status = 'postponed'
    elif quiz_info.get('skipped'):
        status = 'skipped'
    
    user_data['results'].append({
        'question_id': quiz_info['question_id'], 'status': status, 'points_earned': 0,
        'time_taken': SECONDS_PER_QUESTION, 'answered_option_id': None
    })
    
    await send_next_question(chat_id, context)

async def show_final_score(chat_id: int, context: ContextTypes.DEFAULT_TYPE, is_overview: bool = False) -> None:
    user_data = context.user_data
    total_score = user_data.get('total_score', 0)
    results = user_data.get('results', [])
    
    correct_count = sum(1 for r in results if r['status'] == 'correct')
    wrong_count = sum(1 for r in results if r['status'] == 'wrong')
    total_time_taken = sum(r['time_taken'] for r in results)
    total_quiz_time = QUESTIONS_PER_QUIZ * SECONDS_PER_QUESTION
    
    accuracy = 0
    if (correct_count + wrong_count) > 0:
        accuracy = (correct_count / (correct_count + wrong_count)) * 100

    if is_overview:
        overview_text = (
            f"✨ 📊 <b>𝕆𝕍𝔼ℝ𝕍𝕀𝔼𝕎</b> 📊 ✨\n\n"
            f"Total Score     »  <code>{total_score}</code>\n"
            f"Accuracy        »  <code>{accuracy:.1f}%</code>\n"
            f"Correct Answers »  <code>{correct_count}/{len(results)}</code>"
        )
        await context.bot.send_message(chat_id, text=overview_text, parse_mode='HTML')
        # user_data.clear() # Don't clear here, allow trying again.
        return

    score_text = (
        f"⫷ 🏆 <b>𝐅𝐈𝐍𝐀𝐋 𝐒𝐂𝐎𝐑𝐄</b> 🏆 ⫸\n\n"
        f"    ✅ Correct       »  <code>{correct_count}</code>\n"
        f"    ❌ Wrong         »  <code>{wrong_count}</code>\n\n"
        f"    ✪ <b>Total Points</b>  »  <code>{total_score}</code>\n"
        f"....................................................\n"
        f"     📊 <b>𝕄𝕠𝕣𝕖 𝕀𝕟𝕗𝕠𝕣𝕞𝕒𝕥𝕚𝕠𝕟</b> 📊\n\n"
        f"    ⏳ Total Quiz Time   »  <code>{total_quiz_time}s</code>\n"
        f"    ⏱️ Your Time Taken   »  <code>{total_time_taken:.1f}s</code>\n"
        f"    ⇨ Time Saved        »  <code>{total_quiz_time - total_time_taken:.1f}s</code>"
    )
    
    keyboard = [[InlineKeyboardButton("📊 Detailed Review Your Answers", callback_data='detailed_review')],
                [InlineKeyboardButton("🔄      Try Again      🔄", callback_data='try_again')]]
    
    await context.bot.send_message(
        chat_id, text=score_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML'
    )

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
