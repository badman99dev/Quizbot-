import logging
import os
import json
import asyncio
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, PollHandler, PollAnswerHandler, ContextTypes, JobQueue

# Import our custom modules
from quiz_manager import get_quiz_set, get_all_sets
from play_quiz import QuizSession
from user_quiz_data import format_detailed_review

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# This dictionary will hold active quiz sessions, with chat_id as the key.
ACTIVE_SESSIONS = {}

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command by showing a menu of available quizzes."""
    quiz_sets = get_all_sets() # This will now talk to our smart cache manager
    if not quiz_sets:
        await update.message.reply_text("Sorry, no quizzes are available at the moment. Please check back later.")
        return

    keyboard = []
    row = []
    for set_id, data in quiz_sets.items():
        # Make sure 'name' exists to avoid errors
        quiz_name = data.get('name', f"Quiz {set_id}")
        row.append(InlineKeyboardButton(quiz_name, callback_data=f'start_quiz:{set_id}'))
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
        quiz_data = get_quiz_set(set_id) # This talks to our smart cache manager
        if not quiz_data:
            await query.message.reply_text("<b>Error:</b> Requested quiz bank not available.", parse_mode='HTML')
            return

        # Clean up previous messages
        if action == 'try_again':
            try: await query.message.delete()
            except BadRequest: pass
            await context.bot.send_message(chat_id, text=f"🚀 Getting the '<b>{escape(quiz_data['name'])}</b>' quiz ready...", parse_mode='HTML')
        else:
            await query.edit_message_text(text=f"🚀 Getting the '<b>{escape(quiz_data['name'])}</b>' quiz ready...", parse_mode='HTML')

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
        if session and session.active_poll_id:
            poll_id_to_close = session.active_poll_id
            stopped = (action == 'stop_quiz')
            postponed = (action == 'postpone_question')
            skipped = (action == 'skip_permanently')
            await session.handle_closure(poll_id=poll_id_to_close, stopped=stopped, postponed=postponed, skipped=skipped)
            if stopped:
                ACTIVE_SESSIONS.pop(chat_id, None)

async def poll_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Passes poll answers to the correct game session."""
    poll_id = update.poll_answer.poll_id
    if poll_id in context.bot_data:
        session = context.bot_data[poll_id].get('session')
        if session:
            await session.handle_answer(update)
            # If the quiz is over after this answer, remove the session
            if not getattr(session, 'questions_queue', True) and not getattr(session, 'is_suspended', False):
                ACTIVE_SESSIONS.pop(session.chat_id, None)

def main() -> None:
    """Initializes and runs the bot with the reliable JobQueue."""
    TOKEN = os.getenv("TOKEN")
    if not TOKEN:
        raise ValueError("TOKEN environment variable not set! Please set it in Render's environment variables.")
    
    # Initialize the JobQueue for our internal timers
    job_queue = JobQueue()
    application = Application.builder().token(TOKEN).job_queue(job_queue).build()
    
    # Register all the necessary handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(PollAnswerHandler(poll_answer_handler))
    # We no longer need PollHandler for timeouts, as it's handled internally

    print("Bot is running with Smart Cache and reliable inactivity detection...")
    application.run_polling()

if __name__ == '__main__':
    main()
