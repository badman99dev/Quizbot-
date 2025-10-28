
import logging
import os
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, PollHandler, PollAnswerHandler, ContextTypes

# Import our custom modules
from quiz_manager import get_quiz_set, get_all_sets
from play_quiz import QuizSession
from user_quiz_data import format_detailed_review

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# This dictionary will hold active quiz sessions, with chat_id as the key.
# This allows the bot to handle multiple users playing at the same time.
ACTIVE_SESSIONS = {}

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command by showing a menu of available quizzes."""
    quiz_sets = get_all_sets()
    keyboard = []
    row = []
    for set_id, data in quiz_sets.items():
        row.append(InlineKeyboardButton(data['name'], callback_data=f'start_quiz:{set_id}'))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    message_entity = update.message or update.callback_query.message
    await message_entity.reply_text(
        "🎲 Welcome to the Quiz Bot! 🎲\n\nPlease select a quiz to start:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles all button clicks and directs them to the correct action."""
    query = update.callback_query
    await query.answer()
    data = query.data.split(':', 1)
    action = data[0]
    chat_id = update.effective_chat.id

    if action == 'start_quiz' or action == 'try_again':
        set_id = data[1]
        quiz_data = get_quiz_set(set_id)
        if not quiz_data:
            await query.message.reply_text("<b>Error:</b> Requested quiz bank not available.", parse_mode='HTML')
            return

        # Clean up previous messages
        if action == 'try_again':
            try: await query.message.delete()
            except BadRequest: pass
            await context.bot.send_message(chat_id, text=f"🚀 Getting the '<b>{quiz_data['name']}</b>' quiz ready...")
        else:
            await query.edit_message_text(text=f"🚀 Getting the '<b>{quiz_data['name']}</b>' quiz ready...")

        # Create and start a new game session
        session = QuizSession(context, chat_id, set_id, quiz_data)
        ACTIVE_SESSIONS[chat_id] = session
        await session.start()
    
    elif action == 'detailed_review':
        session_id = data[1]
        try:
            with open(f"results/{session_id}.json", "r") as f:
                stored_data = json.load(f)
        except FileNotFoundError:
            await context.bot.send_message(chat_id, "⚠️ The data for this quiz has expired and is no longer available.")
            return

        # Ask the "Artist" to format the review
        message_chunks = format_detailed_review(stored_data['results'], stored_data['quiz_name'], stored_data['questions_data'])
        for chunk in message_chunks:
            await context.bot.send_message(chat_id, text=chunk, parse_mode='HTML')
            await asyncio.sleep(0.5)

    elif action in ['postpone_question', 'skip_permanently', 'stop_quiz']:
        session = ACTIVE_SESSIONS.get(chat_id)
        # Check if there is an active session and if the poll belongs to it
        if session and session.active_poll_id in context.bot_data:
            quiz_info = context.bot_data.pop(session.active_poll_id, None)
            if not quiz_info: return
            
            stopped = (action == 'stop_quiz')
            if action == 'postpone_question': quiz_info['postponed'] = True
            elif action == 'skip_permanently': quiz_info['skipped'] = True
            
            await session.handle_closure(quiz_info, stopped=stopped)
            if stopped:
                ACTIVE_SESSIONS.pop(chat_id, None)

async def poll_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Passes poll answers to the correct game session."""
    poll_id = update.poll_answer.poll_id
    if poll_id in context.bot_data:
        session = context.bot_data[poll_id]['session']
        await session.handle_answer(update)
        # If the quiz is over, remove the session
        if not session.questions_queue:
            ACTIVE_SESSIONS.pop(session.chat_id, None)

async def poll_timeout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Passes poll timeouts to the correct game session."""
    poll_id = update.poll.id
    if poll_id in context.bot_data and update.poll.is_closed:
        session = context.bot_data[poll_id]['session']
        quiz_info = context.bot_data.pop(poll_id, None)
        if not quiz_info: return
        await session.handle_closure(quiz_info)
        # If the quiz is over, remove the session
        if not session.questions_queue:
            ACTIVE_SESSIONS.pop(session.chat_id, None)

def main() -> None:
    """Initializes and runs the bot."""
    TOKEN = os.getenv("TOKEN")
    if not TOKEN:
        raise ValueError("TOKEN environment variable not set! Please set it in Render's environment variables.")
    
    application = Application.builder().token(TOKEN).build()

    # Register all the handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(PollAnswerHandler(poll_answer_handler))
    application.add_handler(PollHandler(poll_timeout_handler))

    # Start the bot
    print("Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
