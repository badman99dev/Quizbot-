import asyncio
import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, PollHandler, PollAnswerHandler, ContextTypes

# --- Configuration ---
QUIZ_NAME = "12th Test"
QUESTIONS_PER_QUIZ = 5
SECONDS_PER_QUESTION = 15

# --- Dummy Questions ---
dummy_questions = [
    {"question": "भारत की राजधानी क्या है?", "options": ["मुंबई", "नई दिल्ली", "चेन्नई", "कोलकाता"], "correct_option_id": 1},
    {"question": "Python में लिस्ट बनाने के लिए किस ब्रैकेट का उपयोग किया जाता है?", "options": ["{}", "()", "[]", "<>"], "correct_option_id": 2},
    {"question": "सूर्य किस दिशा में उगता है?", "options": ["पश्चिम", "उत्तर", "पूर्व", "दक्षिण"], "correct_option_id": 2},
    {"question": "1 KB में कितने बाइट्स होते हैं?", "options": ["1000", "1024", "2048", "512"], "correct_option_id": 1},
    {"question": "इनमें से कौन सा एक सर्च इंजन नहीं है?", "options": ["Google", "Yahoo", "Instagram", "Bing"], "correct_option_id": 2}
]

# --- Bot Logic ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    keyboard = [[InlineKeyboardButton("✅ I'm ready!", callback_data='start_quiz')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"🎲 Get ready for the quiz '{QUIZ_NAME}'\n\n"
        f"🖊 {QUESTIONS_PER_QUIZ} questions\n"
        f"⏱ {SECONDS_PER_QUESTION} seconds per question\n\n"
        f"🏁 Press the button below when you are ready.",
        reply_markup=reply_markup
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if query.data == 'start_quiz':
        await query.edit_message_text(text="🚀 Getting the quiz ready...")
        context.user_data.update({
            'current_question_index': 0, 'correct_answers': 0, 'wrong_answers': 0,
            'quiz_start_time': asyncio.get_event_loop().time(),
        })
        await start_countdown_and_quiz(update.effective_chat.id, context)
    elif query.data == 'try_again':
        await query.message.delete()
        await start_command(update.effective_message, context)

# --- FEATURE 1: Animated Countdown ---
async def start_countdown_and_quiz(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a single message and edits it to create a countdown animation."""
    await context.bot.send_chat_action(chat_id, action='typing')
    msg = await context.bot.send_message(chat_id, text="Get Ready... 3️⃣")
    await asyncio.sleep(1)
    await msg.edit_text("Get Ready... 2️⃣")
    await asyncio.sleep(1)
    await msg.edit_text("Get Ready... 1️⃣")
    await asyncio.sleep(1)
    await msg.edit_text("🚦 GO!")
    await asyncio.sleep(0.5)
    await msg.delete()
    await send_next_question(chat_id, context)

async def send_next_question(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends the next question with a progress bar or the final score."""
    current_index = context.user_data.get('current_question_index', 0)

    if current_index < QUESTIONS_PER_QUIZ:
        # --- FEATURE 2: Progress Bar ---
        progress = int(((current_index + 1) / QUESTIONS_PER_QUIZ) * 10)
        progress_bar = '🟩' * progress + '⬜️' * (10 - progress)

        question_data = dummy_questions[current_index]
        question_text = (
            f"Question {current_index + 1}/{QUESTIONS_PER_QUIZ}\n"
            f"{progress_bar}\n\n"
            f"{question_data['question']}"
        )

        # --- FEATURE 3: Typing Indicator ---
        await context.bot.send_chat_action(chat_id, action='typing')
        message = await context.bot.send_poll(
            chat_id=chat_id,
            question=question_text,
            options=question_data["options"],
            type='quiz',
            correct_option_id=question_data["correct_option_id"],
            open_period=SECONDS_PER_QUESTION,
            is_anonymous=False
        )
        context.bot_data[message.poll.id] = {
            "chat_id": chat_id, "correct_option_id": question_data["correct_option_id"],
            "question_index": current_index
        }
    else:
        await show_final_score(chat_id, context)

async def poll_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    answer = update.poll_answer
    poll_id = answer.poll_id
    if poll_id in context.bot_data:
        quiz_info = context.bot_data.pop(poll_id)
        chat_id = quiz_info["chat_id"]
        if quiz_info["question_index"] != context.user_data.get('current_question_index'):
            return
        if answer.option_ids[0] == quiz_info["correct_option_id"]:
            context.user_data['correct_answers'] += 1
        else:
            context.user_data['wrong_answers'] += 1
        context.user_data['current_question_index'] += 1
        await asyncio.sleep(1.5)
        await send_next_question(chat_id, context)

async def poll_timeout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    poll_id = update.poll.id
    if poll_id in context.bot_data and update.poll.is_closed:
        quiz_info = context.bot_data.pop(poll_id)
        chat_id = quiz_info["chat_id"]
        if quiz_info["question_index"] != context.user_data.get('current_question_index'):
            return
        logger.info(f"Poll {poll_id} timed out.")
        context.user_data['current_question_index'] += 1
        await send_next_question(chat_id, context)

async def show_final_score(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Calculates and shows the final score with better emojis and a dynamic button."""
    correct = context.user_data.get('correct_answers', 0)
    wrong = context.user_data.get('wrong_answers', 0)
    total_answered = correct + wrong
    missed = QUESTIONS_PER_QUIZ - total_answered
    end_time = asyncio.get_event_loop().time()
    total_time = round(end_time - context.user_data.get('quiz_start_time', 0))

    # --- FEATURE 4: Better Emojis in Score ---
    score_text = (
        f"🏁 **The quiz has finished!** 🏆\n\n"
        f"Here's your score:\n\n"
        f"✅ **Correct** – `{correct}`\n"
        f"❌ **Wrong** – `{wrong}`\n"
        f"⌛️ **Missed** – `{missed}`\n"
        f"⏱ **Total Time** – `{total_time} sec`\n\n"
        "Great effort!"
    )
    keyboard = [[InlineKeyboardButton("🔄 Try Again", callback_data='try_again')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_chat_action(chat_id, action='typing')
    msg = await context.bot.send_message(
        chat_id, text=score_text, reply_markup=reply_markup, parse_mode='Markdown'
    )
    context.user_data.clear()

    # --- FEATURE 5: Dynamic "Try Again" Button ---
    await asyncio.sleep(10) # Wait for 10 seconds
    try:
        new_keyboard = [[InlineKeyboardButton("🏆 Go for a better score!", callback_data='try_again')]]
        await msg.edit_reply_markup(reply_markup=InlineKeyboardMarkup(new_keyboard))
    except Exception as e:
        logger.info(f"Could not edit the 'Try Again' button, probably it was interacted with: {e}")

def main() -> None:
    TOKEN = os.getenv("TELEGRAM_TOKEN")
    if not TOKEN:
        raise ValueError("Error: TELEGRAM_TOKEN environment variable is not set!")
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(PollAnswerHandler(poll_answer_handler))
    application.add_handler(PollHandler(poll_timeout_handler))
    application.run_polling()

if __name__ == '__main__':
    main()
