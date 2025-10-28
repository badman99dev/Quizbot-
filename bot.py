import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, PollAnswerHandler, ContextTypes

# --- कॉन्फ़िगरेशन ---
QUIZ_NAME = "12th Test"
QUESTIONS_PER_QUIZ = 2  # तुम इसे dummy_questions की लंबाई तक बढ़ा सकते हो
SECONDS_PER_QUESTION = 15

# --- डमी सवाल (Dummy Questions) ---
# तुम यहाँ जितने चाहो उतने सवाल जोड़ सकते हो।
# correct_option_id इंडेक्स 0 से शुरू होता है (0 मतलब पहला ऑप्शन, 1 मतलब दूसरा, etc.)
dummy_questions = [
    {
        "question": "भारत की राजधानी क्या है?",
        "options": ["मुंबई", "नई दिल्ली", "चेन्नई", "कोलकाता"],
        "correct_option_id": 1,
    },
    {
        "question": "Python में लिस्ट बनाने के लिए किस ब्रैकेट का उपयोग किया जाता है?",
        "options": ["{}", "()", "[]", "<>"],
        "correct_option_id": 2,
    },
    {
        "question": "सूर्य किस दिशा में उगता है?",
        "options": ["पश्चिम", "उत्तर", "पूर्व", "दक्षिण"],
        "correct_option_id": 2,
    },
    {
        "question": "1 KB में कितने बाइट्स होते हैं?",
        "options": ["1000", "1024", "2048", "512"],
        "correct_option_id": 1,
    },
    {
        "question": "इनमें से कौन सा एक सर्च इंजन नहीं है?",
        "options": ["Google", "Yahoo", "Instagram", "Bing"],
        "correct_option_id": 2,
    }
]

# --- बॉट का लॉजिक ---

# लॉगिंग सेटअप
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start कमांड हैंडलर। क्विज़ शुरू करने का मैसेज भेजता है।"""
    user = update.effective_user
    context.user_data.clear() # पुराने क्विज़ डेटा को साफ़ करें

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
    """बटन क्लिक को हैंडल करता है।"""
    query = update.callback_query
    await query.answer() # बटन क्लिक का कन्फर्मेशन

    if query.data == 'start_quiz':
        await query.edit_message_text(text="🚀 Starting quiz...")
        await start_countdown_and_quiz(update.effective_chat.id, context)

    elif query.data == 'try_again':
        # दोबारा क्विज़ शुरू करने के लिए स्टार्ट मैसेज फिर से भेजें
        context.user_data.clear()
        keyboard = [[InlineKeyboardButton("✅ I'm ready!", callback_data='start_quiz')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text(
            f"🎲 Get ready for the quiz '{QUIZ_NAME}'\n\n"
            f"🖊 {QUESTIONS_PER_QUIZ} questions\n"
            f"⏱ {SECONDS_PER_QUESTION} seconds per question\n\n"
            f"🏁 Press the button below when you are ready.",
            reply_markup=reply_markup
        )
        await query.delete_message()


async def start_countdown_and_quiz(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """काउंटडाउन शुरू करता है और फिर क्विज़ का पहला सवाल भेजता है।"""
    # यूजर डेटा इनिशियलाइज़ करें
    context.user_data['current_question_index'] = 0
    context.user_data['correct_answers'] = 0
    context.user_data['wrong_answers'] = 0
    context.user_data['quiz_start_time'] = asyncio.get_event_loop().time()


    # काउंटडाउन
    await context.bot.send_message(chat_id, text="3...")
    await asyncio.sleep(1)
    await context.bot.send_message(chat_id, text="2 READY?...")
    await asyncio.sleep(1)
    await context.bot.send_message(chat_id, text="1 SET...")
    await asyncio.sleep(1)
    await context.bot.send_message(chat_id, text="GO 🚀")
    
    await send_next_question(chat_id, context)

async def send_next_question(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """अगला सवाल भेजता है या क्विज़ खत्म करता है।"""
    idx = context.user_data.get('current_question_index', 0)

    if idx < QUESTIONS_PER_QUIZ and idx < len(dummy_questions):
        question_data = dummy_questions[idx]
        
        message = await context.bot.send_poll(
            chat_id=chat_id,
            question=question_data["question"],
            options=question_data["options"],
            type='quiz',
            correct_option_id=question_data["correct_option_id"],
            open_period=SECONDS_PER_QUESTION,
            is_anonymous=False # यह ज़रूरी है PollAnswerHandler के लिए
        )
        
        # पोल आईडी को स्टोर करें ताकि हम जवाब को ट्रैक कर सकें
        context.user_data['current_poll_id'] = message.poll.id
    else:
        await show_final_score(chat_id, context)

async def poll_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """यूजर के जवाब को हैंडल करता है।"""
    answer = update.poll_answer
    
    # सुनिश्चित करें कि यह हमारे क्विज़ का ही जवाब है
    if answer.poll_id != context.user_data.get('current_poll_id'):
        return

    # सही जवाब का इंडेक्स निकालें
    current_idx = context.user_data['current_question_index']
    correct_option_id = dummy_questions[current_idx]['correct_option_id']
    
    # स्कोर अपडेट करें
    if answer.option_ids and answer.option_ids[0] == correct_option_id:
        context.user_data['correct_answers'] += 1
    else:
        context.user_data['wrong_answers'] += 1

    # अगला सवाल भेजें
    context.user_data['current_question_index'] += 1
    # थोड़ा इंतज़ार करें ताकि यूजर देख सके कि जवाब सही था या गलत
    await asyncio.sleep(1.5) 
    await send_next_question(update.effective_chat.id, context)


async def show_final_score(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """क्विज़ के अंत में फाइनल स्कोर दिखाता है।"""
    correct = context.user_data.get('correct_answers', 0)
    wrong = context.user_data.get('wrong_answers', 0)
    total_answered = correct + wrong
    missed = QUESTIONS_PER_QUIZ - total_answered

    end_time = asyncio.get_event_loop().time()
    total_time = round(end_time - context.user_data.get('quiz_start_time', end_time))
    
    score_text = (
        f"🏁 The quiz '{QUIZ_NAME}' has finished!\n\n"
        f"You answered {total_answered} questions:\n\n"
        f"✅ Correct – {correct}\n"
        f"❌ Wrong – {wrong}\n"
        f"⌛️ Missed – {missed}\n"
        f"⏱ {total_time} sec\n\n"
        "🥇1st place out of 1." # अभी के लिए यह स्टैटिक है
    )

    keyboard = [[InlineKeyboardButton("🔄 Try Again", callback_data='try_again')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(chat_id, text=score_text, reply_markup=reply_markup)
    context.user_data.clear() # सेशन क्लियर करें

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/stop कमांड से क्विज़ को रोकता है।"""
    await update.message.reply_text("Quiz stopped. Send /start to begin a new one.")
    context.user_data.clear()


def main() -> None:
    """बॉट को शुरू करता है।"""
    # अपने बॉट का टोकन यहाँ डालें
    TOKEN = "8045438791:AAE4KoPRdQmDZ4qZNq4BzMWCEmAm-c6i-ik" # 👈 अपना टोकन यहाँ डालो!
    
    application = Application.builder().token(TOKEN).build()

    # कमांड्स
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stop", stop_command))

    # कॉल-बैक और पोल हैंडलर्स
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(PollAnswerHandler(poll_answer_handler))
    
    # बॉट को चलाएँ
    application.run_polling()


if __name__ == '__main__':
    main()
