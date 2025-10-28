import asyncio
import time
import os
import json
import random
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes
import logging

# --- Constants ---
SECONDS_PER_QUESTION = 15
POINTS_CORRECT = 100
POINTS_WRONG_PENALTY = -25
MAX_SPEED_BONUS = 50
CONSECUTIVE_TIMEOUT_LIMIT = 5  # <<< NEW: Inactivity limit

# --- Helper Functions ---
def calculate_points(time_taken):
    if time_taken < 2: return MAX_SPEED_BONUS
    if time_taken >= SECONDS_PER_QUESTION: return 0
    return int(MAX_SPEED_BONUS * (1 - (time_taken / SECONDS_PER_QUESTION)))

def get_question_by_id_from_data(qid, questions_data):
    return next((q for q in questions_data if q["id"] == qid), None)

# --- The Game Session Class ---
class QuizSession:
    def __init__(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, set_id: str, quiz_data: dict):
        self.context = context
        self.chat_id = chat_id
        self.set_id = set_id
        self.quiz_name = quiz_data['name']
        self.questions_data = list(quiz_data['questions'])
        random.shuffle(self.questions_data)
        self.questions_queue = [q['id'] for q in self.questions_data]
        self.results = []
        self.total_score = 0
        self.active_poll_message_id = None
        self.active_poll_id = None
        self.session_id = f"{chat_id}_{int(time.time())}"
        self.consecutive_timeouts = 0  # <<< NEW: Inactivity counter
        self.is_suspended = False # Flag to prevent multiple final messages

    async def start(self):
        try:
            msg = await self.context.bot.send_message(self.chat_id, text="Get Ready... 3️⃣")
            await asyncio.sleep(1.1); await msg.edit_text("Get Ready... 2️⃣")
            await asyncio.sleep(1.1); await msg.edit_text("Get Ready... 1️⃣")
            await asyncio.sleep(1.1); await msg.edit_text("🚦 GO!")
            await asyncio.sleep(0.5); await msg.delete()
        except BadRequest as e:
            logging.warning(f"Countdown error: {e}")
        await self.send_next_question()

    async def send_next_question(self):
        delete_task = None
        if self.active_poll_message_id:
            delete_task = self.context.bot.delete_message(self.chat_id, self.active_poll_message_id)
        
        if not self.questions_queue:
            if delete_task:
                try: await delete_task
                except BadRequest: pass
            await self.show_final_score()
            return

        question_id = self.questions_queue[0]
        question_data = get_question_by_id_from_data(question_id, self.questions_data)
        total_answered = len(self.results)
        is_postponed = getattr(self, f"is_postponed_{question_id}", False)
        
        keyboard = [[InlineKeyboardButton("⏹️ Stop Quiz", callback_data='stop_quiz')]]
        if is_postponed: keyboard[0].append(InlineKeyboardButton("⏩ Skip Permanently", callback_data='skip_permanently'))
        else: keyboard[0].append(InlineKeyboardButton("➡️ Postpone", callback_data='postpone_question'))

        send_task = self.context.bot.send_poll(
            chat_id=self.chat_id, question=f"Q {total_answered + 1}/{len(self.questions_data)}: {question_data['question']}",
            options=question_data["options"], type='quiz', correct_option_id=question_data["correct_option_id"],
            open_period=SECONDS_PER_QUESTION, is_anonymous=False, reply_markup=InlineKeyboardMarkup(keyboard)
        )
        try:
            if delete_task: _, message = await asyncio.gather(delete_task, send_task)
            else: message = await send_task
        except BadRequest as e:
            logging.error(f"Failed to send next question: {e}")
            return

        self.active_poll_message_id = message.message_id
        self.active_poll_id = message.poll.id
        self.context.bot_data[message.poll.id] = {"session": self, "question_id": question_id, "time_sent": time.time()}
        
        self.context.job_queue.run_once(self.handle_timeout_job, SECONDS_PER_QUESTION + 1, data={'poll_id': message.poll.id}, name=f"timeout_{message.poll.id}")

    async def handle_answer(self, update: Update):
        poll_id = self.active_poll_id
        jobs = self.context.job_queue.get_jobs_by_name(f"timeout_{poll_id}")
        for job in jobs: job.schedule_removal()

        quiz_info = self.context.bot_data.pop(poll_id, None)
        if not quiz_info: return
        
        self.consecutive_timeouts = 0  # <<< NEW: Reset inactivity counter on answer

        answer = update.poll_answer; time_taken = time.time() - quiz_info['time_sent']
        question_id = self.questions_queue.pop(0); question_data = get_question_by_id_from_data(question_id, self.questions_data)
        is_correct = answer.option_ids[0] == question_data["correct_option_id"]
        points, status = (POINTS_CORRECT + calculate_points(time_taken), 'correct') if is_correct else (POINTS_WRONG_PENALTY, 'wrong')
        
        self.total_score += points
        self.results.append({'question_id': question_id, 'status': status, 'points_earned': points, 'time_taken': time_taken, 'answered_option_id': answer.option_ids[0]})
        
        await asyncio.sleep(0.7)
        await self.send_next_question()

    async def handle_timeout_job(self, context: ContextTypes.DEFAULT_TYPE):
        job_data = context.job.data; poll_id = job_data['poll_id']
        if poll_id in self.context.bot_data:
            logging.info(f"Internal timer job triggered for poll {poll_id}. Processing timeout.")
            
            self.consecutive_timeouts += 1  # <<< NEW: Increment inactivity counter
            if self.consecutive_timeouts >= CONSECUTIVE_TIMEOUT_LIMIT:
                await self.suspend_quiz()
                return

            await self.handle_closure(poll_id=poll_id)
        else:
            logging.info(f"Internal timer job for poll {poll_id} ignored (already answered).")
            
    async def handle_closure(self, poll_id: str, stopped=False, postponed=False, skipped=False):
        quiz_info = self.context.bot_data.pop(poll_id, None)
        if not quiz_info or not self.questions_queue: return

        if quiz_info.get("question_id") == self.questions_queue[0]:
            question_id = self.questions_queue.pop(0); status = 'timed_out'
            if postponed: self.questions_queue.append(question_id); setattr(self, f"is_postponed_{question_id}", True); status = 'postponed'
            elif skipped: status = 'skipped'
            elif stopped: status = 'stopped'
            
            if status != 'postponed':
                self.results.append({'question_id': question_id, 'status': status, 'points_earned': 0, 'time_taken': SECONDS_PER_QUESTION, 'answered_option_id': None})
            
            if not self.questions_queue or stopped: await self.show_final_score()
            else: await self.send_next_question()

    async def suspend_quiz(self):
        """NEW: Stops the quiz due to user inactivity."""
        if self.is_suspended: return
        self.is_suspended = True
        
        # Clean up any active poll and timer
        if self.active_poll_id in self.context.bot_data: self.context.bot_data.pop(self.active_poll_id)
        jobs = self.context.job_queue.get_jobs_by_name(f"timeout_{self.active_poll_id}")
        for job in jobs: job.schedule_removal()
        try: await self.context.bot.delete_message(self.chat_id, self.active_poll_message_id)
        except BadRequest: pass

        logging.warning(f"Quiz suspended for chat {self.chat_id} due to inactivity.")
        keyboard = [[InlineKeyboardButton("🔄      Try Again      🔄", callback_data=f'try_again:{self.set_id}')]]
        await self.context.bot.send_message(
            self.chat_id,
            text="⚠️ Quiz session has been suspended due to inactivity.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def show_final_score(self):
        if self.is_suspended: return
        if not os.path.exists('results'): os.makedirs('results')
        data_to_save = {'results': self.results, 'quiz_name': self.quiz_name, 'questions_data': self.questions_data}
        with open(f"results/{self.session_id}.json", "w") as f: json.dump(data_to_save, f, indent=2)
        correct_count = sum(1 for r in self.results if r['status'] == 'correct'); wrong_count = sum(1 for r in self.results if r['status'] == 'wrong')
        score_text = (f"⫷ 🏆 <b>𝐅𝐈𝐍𝐀𝐋 𝐒𝐂𝐎𝐑𝐄 » {escape(self.quiz_name)}</b> 🏆 ⫸\n\n" f"    ✅ Correct       »  <code>{correct_count}</code>\n" f"    ❌ Wrong         »  <code>{wrong_count}</code>\n\n" f"    ✪ <b>Total Points</b>  »  <code>{self.total_score}</code>")
        keyboard = [[InlineKeyboardButton("📊 Detailed Review", callback_data=f'detailed_review:{self.session_id}')], [InlineKeyboardButton("🔄      Try Again      🔄", callback_data=f'try_again:{self.set_id}')]]
        await self.context.bot.send_message(self.chat_id, text=score_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
