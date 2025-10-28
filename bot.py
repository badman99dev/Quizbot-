# bot.py (Final Version)
import logging, os, json, asyncio
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, PollAnswerHandler, ContextTypes, JobQueue

from quiz_manager import get_quiz_set, get_all_sets
from play_quiz import QuizSession
from user_quiz_data import format_detailed_review

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO); logger = logging.getLogger(__name__); ACTIVE_SESSIONS = {}

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    quiz_sets = get_all_sets(); keyboard = []; row = []
    for set_id, data in quiz_sets.items():
        row.append(InlineKeyboardButton(data['name'], callback_data=f'start_quiz:{set_id}'))
        if len(row) == 2: keyboard.append(row); row = []
    if row: keyboard.append(row)
    message_entity = update.message or update.callback_query.message; await message_entity.reply_text("🎲 Welcome to the Quiz Bot! 🎲\n\nPlease select a quiz to start:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query; await query.answer(); data = query.data.split(':', 1); action = data[0]; chat_id = update.effective_chat.id
    if action == 'start_quiz' or action == 'try_again':
        if chat_id in ACTIVE_SESSIONS: # Prevent starting a new quiz while one is active
            await query.answer("A quiz is already in progress in this chat.", show_alert=True)
            return
        set_id = data[1]; quiz_data = get_quiz_set(set_id)
        if not quiz_data: await query.message.reply_text("<b>Error:</b>...", parse_mode='HTML'); return
        if action == 'try_again':
            try: await query.message.delete()
            except BadRequest: pass
            await context.bot.send_message(chat_id, text=f"🚀 Getting the '<b>{escape(quiz_data['name'])}</b>' quiz ready...", parse_mode='HTML')
        else: await query.edit_message_text(text=f"🚀 Getting the '<b>{escape(quiz_data['name'])}</b>' quiz ready...", parse_mode='HTML')
        session = QuizSession(context, chat_id, set_id, quiz_data); ACTIVE_SESSIONS[chat_id] = session; await session.start()
    elif action == 'detailed_review':
        session_id = data[1]
        try:
            with open(f"results/{session_id}.json", "r") as f: stored_data = json.load(f)
        except FileNotFoundError: await context.bot.send_message(chat_id, "⚠️ The data for this quiz has expired..."); return
        message_chunks = format_detailed_review(stored_data['results'], stored_data['quiz_name'], stored_data['questions_data'])
        for chunk in message_chunks: await context.bot.send_message(chat_id, text=chunk, parse_mode='HTML'); await asyncio.sleep(0.5)
    elif action in ['postpone_question', 'skip_permanently', 'stop_quiz']:
        session = ACTIVE_SESSIONS.get(chat_id)
        if session and session.active_poll_id:
            poll_id_to_close = session.active_poll_id; stopped = (action == 'stop_quiz'); postponed = (action == 'postpone_question'); skipped = (action == 'skip_permanently')
            await session.handle_closure(poll_id=poll_id_to_close, stopped=stopped, postponed=postponed, skipped=skipped)
            if stopped: ACTIVE_SESSIONS.pop(chat_id, None)

async def poll_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    poll_id = update.poll_answer.poll_id
    if poll_id in context.bot_data:
        session = context.bot_data[poll_id].get('session')
        if session:
            await session.handle_answer(update, poll_id)
            if not getattr(session, 'questions_queue', True): # Check if quiz ended
                ACTIVE_SESSIONS.pop(session.chat_id, None)

def main() -> None:
    TOKEN = os.getenv("TOKEN"); 
    if not TOKEN: raise ValueError("TOKEN environment variable not set!")
    
    # NEW: Initialize the JobQueue
    job_queue = JobQueue()
    application = Application.builder().token(TOKEN).job_queue(job_queue).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(PollAnswerHandler(poll_answer_handler))
    # Note: We don't need PollHandler anymore, our internal timer is superior.
    
    print("Bot is running with inactivity suspension..."); application.run_polling()

if __name__ == '__main__':
    main()
