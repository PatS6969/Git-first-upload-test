#!/usr/bin/env python3
"""
Bible Trivia Standalone App
- Uses trivia_db.py for SQLite backend
- Supports multiple_choice, true_false, numeric question types
- Prevents question repeats in-session and across sessions
- Shows ad (video/image) before quiz results
- Displays logo instead of text title
- Displays question ID with question
- Deduplicates questions by text to handle DB duplicates
"""
import sys
import os
import random
import logging
import glob
import sqlite3
from pathlib import Path
from datetime import datetime

from PyQt5.QtCore import QCoreApplication
import os, sys

plugin_path = os.path.join(os.path.dirname(sys.executable), "PyQt5", "Qt", "plugins")
QCoreApplication.addLibraryPath(plugin_path)


# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")




def resource_path(relative_path):
    """Get absolute path to resource, works for dev and PyInstaller."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# Ensure trivia_db import
base = Path(__file__).resolve().parent
if str(base) not in sys.path:
    sys.path.insert(0, str(base))
try:
    import trivia_db
except ImportError:
    parent = base.parent
    if str(parent) not in sys.path:
        sys.path.insert(0, str(parent))
    import trivia_db

db_path = resource_path("data/trivia/bible_trivia.db")
conn = sqlite3.connect(db_path)
#trivia_db.initialize_database(db_path)

def show_splash_screen():
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    splash_pix = QPixmap(resource_path("assets/bible_trivia_splash.png"))
    scaled_pix = splash_pix.scaled(800, 700, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    splash = QSplashScreen(scaled_pix, Qt.WindowStaysOnTopHint)
    splash.setWindowFlag(Qt.FramelessWindowHint)
    splash.show()
    return app, splash


from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QMessageBox,
    QProgressBar, QHBoxLayout, QSplashScreen, QLineEdit, QComboBox, QDialog, QGridLayout
)
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent, QSound
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5.QtCore import Qt, QUrl, QTimer


# Sound setup
SOUNDS_DIR = base / "assets" / "Sounds"
_sound_available = False
_sound_correct = None
_sound_wrong = None
try:
    _sound_available = True
    correct_path = resource_path("assets/Sounds/correct.wav")
    wrong_path = resource_path("assets/Sounds/wrong.wav")
    if correct_path and os.path.exists(correct_path):
        _sound_correct = str(correct_path)
    if wrong_path and os.path.exists(wrong_path):
        _sound_wrong = str(wrong_path)
except Exception as e:
    logging.warning(f"Failed to set up sounds: {e}")


def play_correct_sound():
    if _sound_correct and _sound_available:
        try:
            QSound.play(_sound_correct)
            logging.debug("Played correct sound")
        except Exception as e:
            logging.warning(f"Failed to play correct sound: {e}")

def play_wrong_sound():
    if _sound_wrong and _sound_available:
        try:
            QSound.play(_sound_wrong)
            logging.debug("Played wrong sound")
        except Exception as e:
            logging.warning(f"Failed to play wrong sound: {e}")

# Numeric word converter
_num_words = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "hundred": 100
}

def word_to_number(text):
    """Convert text like 'twelve' or '12' to integer."""
    if text is None:
        return None
    t = str(text).strip().lower().replace('-', ' ')
    if t.isdigit():
        try:
            return int(t)
        except Exception:
            return None
    parts = t.split()
    total = 0
    current = 0
    for p in parts:
        if p in _num_words:
            val = _num_words[p]
            if val == 100:
                current = max(1, current) * 100
            else:
                current += val
        else:
            try:
                num = int(''.join(ch for ch in p if ch.isdigit()))
                current += num
            except Exception:
                return None
    total += current
    return total if total != 0 else (0 if t in ('zero', '0') else None)

class AdDialog(QDialog):
    """Dialog to display a random ad (video or image) before quiz results."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Advertisement")
        self.setFixedSize(600, 400)
        self.setModal(True)
        self.media_player = QMediaPlayer(self)
        self.video_widget = QVideoWidget(self)
        self.media_player.setVideoOutput(self.video_widget)
        self.media_player.error.connect(self.handle_media_error)
        self.skip_button = QPushButton("Skip Ad")
        self.skip_button.clicked.connect(self.accept)
        self.skip_button.setEnabled(False)
        self.skip_button.setVisible(False)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.enable_skip)
        layout = QVBoxLayout()
        layout.addWidget(self.video_widget)
        layout.addWidget(self.skip_button, alignment=Qt.AlignRight)
        self.setLayout(layout)
        self.ad_files = []
        self.load_ads()

    def load_ads(self):
        """Load valid media files from ads directory."""
        ad_dir = resource_path("assets/ads")
        valid_extensions = ('.mp4', '.avi', '.mov', '.wmv', '.jpg', '.png', '.jpeg')
        self.ad_files = [f for f in glob.glob(f"{ad_dir}/*.*") if f.lower().endswith(valid_extensions)]
        if not self.ad_files:
            default_ad = resource_path("assets/ads/Bible_Trivia_Ads.mp4")
            if Path(default_ad).exists():
                self.ad_files = [default_ad]
        logging.info(f"Loaded {len(self.ad_files)} valid ad(s): {self.ad_files}")

    def handle_media_error(self, error):
        """Log media playback errors."""
        logging.error(f"Media playback error: {self.media_player.errorString()} ({error})")
        if hasattr(self, 'current_ad') and self.current_ad in self.ad_files:
            self.ad_files.remove(self.current_ad)
        self.play_ad()

    def play_ad(self):
        """Play a random valid ad (video or image)."""
        if not self.ad_files:
            logging.warning("No valid ads available")
            self.accept()
            return
        self.current_ad = random.choice(self.ad_files)
        logging.info(f"Attempting to play ad: {self.current_ad}")
        print("Resolved ad path:", self.current_ad)
        print("File exists:", Path(self.current_ad).exists())
        try:
            if self.current_ad.lower().endswith(('.jpg', '.png', '.jpeg')):
                pixmap = QPixmap(self.current_ad).scaled(self.video_widget.size(), Qt.KeepAspectRatio)
                self.video_widget.setPixmap(pixmap)
                self.timer.start(10000)
                self.skip_button.setVisible(True)
                self.skip_button.setEnabled(True)
            else:
                self.media_player.setMedia(QMediaContent(QUrl.fromLocalFile(self.current_ad)))
                self.media_player.play()
                self.timer.start(20000)
                self.media_player.stateChanged.connect(self.on_media_finished)
        except Exception as e:
            logging.error(f"Failed to play ad {self.current_ad}: {e}")
            if self.current_ad in self.ad_files:
                self.ad_files.remove(self.current_ad)
            self.play_ad()

    def enable_skip(self):
        """Show and enable the skip button after timeout."""
        self.skip_button.setVisible(True)
        self.skip_button.setEnabled(True)
        self.timer.stop()

    def on_media_finished(self, state):
        """Close dialog when video ends."""
        if state == QMediaPlayer.StoppedState:
            self.accept()

    def showEvent(self, event):
        """Start ad playback when dialog is shown."""
        super().showEvent(event)
        self.play_ad()



class StartupDialog(QDialog):
    """Dialog for selecting quiz options."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bible Trivia — Start")
        self.setFixedSize(420, 250)
        self.setModal(True)
        self.setup_ui()
        self.chosen_limit = 10
        self.chosen_difficulty = None
        self.chosen_reset_period = None

    def setup_ui(self):
        layout = QVBoxLayout()
        title = QLabel()
        logo_path = resource_path("assets/bible_trivia_logo.png")
        pixmap = QPixmap(logo_path).scaled(200, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        title.setPixmap(pixmap)
        title.setAlignment(Qt.AlignCenter)
        subtitle = QLabel("Choose difficulty, number of questions, and reset period")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        grid = QGridLayout()
        grid.setContentsMargins(20, 10, 20, 10)

        diff_label = QLabel("Difficulty:")
        self.diff_box = QComboBox()
        self.diff_box.addItems(["Mixed", "Easy", "Medium", "Hard"])
        grid.addWidget(diff_label, 0, 0)
        grid.addWidget(self.diff_box, 0, 1)

        count_label = QLabel("Number of Questions:")
        self.count_box = QComboBox()
        for n in range(10, 101, 10):
            self.count_box.addItem(str(n))
        self.count_box.setCurrentIndex(1)
        grid.addWidget(count_label, 1, 0)
        grid.addWidget(self.count_box, 1, 1)

        reset_label = QLabel("Reset Used Questions After:")
        self.reset_box = QComboBox()
        self.reset_box.addItems(["60 days", "90 days", "Never"])
        reset_days = trivia_db.get_reset_period()
        idx = 0 if reset_days == 60 else 1 if reset_days == 90 else 2
        self.reset_box.setCurrentIndex(idx)
        grid.addWidget(reset_label, 2, 0)
        grid.addWidget(self.reset_box, 2, 1)

        layout.addLayout(grid)

        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("Start Quiz")
        self.start_btn.clicked.connect(self.accept_and_start)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch(1)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.start_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def accept_and_start(self):
        self.chosen_difficulty = self.diff_box.currentText().lower().strip()
        if self.chosen_difficulty == "mixed":
            self.chosen_difficulty = None
        try:
            self.chosen_limit = int(self.count_box.currentText())
        except Exception:
            self.chosen_limit = 10
        reset_text = self.reset_box.currentText()
        self.chosen_reset_period = 60 if "60" in reset_text else 90 if "90" in reset_text else None
        trivia_db.set_reset_period(self.chosen_reset_period)
        self.accept()

    
import sqlite3
def check_trivia_table():
    conn = sqlite3.connect(resource_path("data/trivia/bible_trivia.db"), timeout=10)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM trivia")
    count = cursor.fetchone()[0]
    conn.close()
    if count == 0:
        print("Error: No questions in trivia table. Run import_to_db.py.")
        exit(1)
    return count

class TriviaWindow(QWidget):
    """Main quiz window."""
    def __init__(self, questions):
        super().__init__()
        # Deduplicate by both ID and question text
        seen_ids = set()
        seen_questions = set()
        deduplicated_questions = []
        for q in questions:
            question_text = str(q.get('question', '')).strip().lower()
            if q['id'] not in seen_ids and question_text not in seen_questions:
                deduplicated_questions.append(q)
                seen_ids.add(q['id'])
                seen_questions.add(question_text)
            else:
                logging.warning(f"Skipped duplicate question: ID {q['id']}, Text: {question_text[:50]}{'...' if len(question_text) > 50 else ''}")
        self.questions = deduplicated_questions
        self.total_questions = len(self.questions)
        self.current_index = 0
        self.score = 0
        self.correct_option_index = None
        self.used_question_ids = set()
        self.setWindowTitle("Bible Trivia")
        self.setMinimumSize(760, 520)
        self.setup_ui()
        self.apply_styles()
        self.progress_bar.setMaximum(max(1, self.total_questions))
        self.progress_bar.setValue(0)
        if self.total_questions > 0:
            logging.info(f"Loaded {self.total_questions} questions: {[q['id'] for q in self.questions]}")
            self.load_question()
        else:
            QMessageBox.information(self, "No Questions", "No questions available for the selected options.")

    def setup_ui(self):
        self.layout = QVBoxLayout()
        header = QLabel()
        logo_path = resource_path("assets/bible_trivia_logo.png")
        pixmap = QPixmap(logo_path).scaled(300, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        header.setPixmap(pixmap)
        header.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(header)

        self.meta_label = QLabel("")
        self.meta_label.setFont(QFont("Segoe UI", 10))
        self.meta_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.meta_label)

        self.question_label = QLabel("")
        self.question_label.setWordWrap(True)
        self.question_label.setFont(QFont("Segoe UI", 16))
        self.question_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.question_label)

        self.option_buttons = []
        opts_layout = QVBoxLayout()
        for i in range(4):
            btn = QPushButton(f"Option {i+1}")
            btn.setFont(QFont("Segoe UI", 14))
            btn.clicked.connect(lambda _, idx=i: self.handle_multiple_choice(idx))
            btn.setVisible(False)
            self.option_buttons.append(btn)
            opts_layout.addWidget(btn)
        self.layout.addLayout(opts_layout)

        tf_layout = QHBoxLayout()
        self.true_btn = QPushButton("True")
        self.true_btn.setFont(QFont("Segoe UI", 14))
        self.true_btn.clicked.connect(lambda: self.handle_true_false("True"))
        self.false_btn = QPushButton("False")
        self.false_btn.setFont(QFont("Segoe UI", 14))
        self.false_btn.clicked.connect(lambda: self.handle_true_false("False"))
        tf_layout.addWidget(self.true_btn)
        tf_layout.addWidget(self.false_btn)
        self.layout.addLayout(tf_layout)

        num_layout = QHBoxLayout()
        self.numeric_input = QLineEdit()
        self.numeric_input.setPlaceholderText("Type your answer (e.g. 12 or Twelve)")
        self.numeric_submit = QPushButton("Submit")
        self.numeric_submit.clicked.connect(self.handle_numeric_submit)
        num_layout.addWidget(self.numeric_input)
        num_layout.addWidget(self.numeric_submit)
        self.layout.addLayout(num_layout)

        bottom = QHBoxLayout()
        self.score_label = QLabel("Score: 0")
        self.progress_bar = QProgressBar()
        bottom.addWidget(self.score_label)
        bottom.addWidget(self.progress_bar)
        self.layout.addLayout(bottom)

        nav = QHBoxLayout()
        self.prev_btn = QPushButton("Previous")
        self.prev_btn.clicked.connect(self.go_previous)
        self.next_btn = QPushButton("Next")
        self.next_btn.clicked.connect(self.skip_question)
        self.restart_btn = QPushButton("Restart")
        self.restart_btn.clicked.connect(self.restart_quiz)
        nav.addWidget(self.prev_btn)
        nav.addWidget(self.next_btn)
        nav.addStretch(1)
        nav.addWidget(self.restart_btn)
        self.layout.addLayout(nav)

        self.setLayout(self.layout)

    def apply_styles(self):
        self.setStyleSheet("""
            QWidget { background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, stop:0 #0f1720, stop:1 #071026); color: #e6eef8; }
            QLabel { color: #e6eef8; }
            QPushButton { background-color: #1f6feb; color: white; border-radius: 8px; padding: 8px; }
            QPushButton:hover { background-color: #155bb5; }
            QLineEdit { background-color: #0b1720; color: #fff; padding:8px; border-radius:6px; }
            QProgressBar { background: #0b1720; color: #fff; border-radius:6px; height:14px; }
        """)

    def reset_widgets(self):
        for b in self.option_buttons:
            b.setVisible(False)
            b.setEnabled(True)
        self.true_btn.setVisible(False)
        self.false_btn.setVisible(False)
        self.numeric_input.setVisible(False)
        self.numeric_submit.setVisible(False)
        self.numeric_input.clear()
        self.correct_option_index = None

    def load_question(self):
        if not self.questions or self.current_index >= self.total_questions:
            self.finish_quiz()
            return
        self.reset_widgets()
        while self.current_index < self.total_questions:
            q = self.questions[self.current_index]
            if q['id'] not in self.used_question_ids:
                self.used_question_ids.add(q['id'])
                question_snippet = q.get('question', '')[:50] + ('...' if len(q.get('question', '')) > 50 else '')
                logging.debug(f"Displaying question ID {q['id']}: {question_snippet}")
                break
            else:
                logging.warning(f"Skipping duplicate question ID {q['id']} at index {self.current_index}")
            self.current_index += 1
        if self.current_index >= self.total_questions:
            self.finish_quiz()
            return
        q = self.questions[self.current_index]
        self.meta_label.setText(f"{q.get('category','')} — {q.get('book','')} — ID: {q['id']}")
        self.question_label.setText(q.get('question',''))
        qtype = q.get('question_type','multiple_choice')
        if qtype == 'multiple_choice':
            options = q.get('options') or []
            while len(options) < 4:
                options.append('N/A')
            paired = list(enumerate(options))
            random.shuffle(paired)
            correct_text = str(q.get('correct_answer','')).strip().lower()
            self.correct_option_index = None
            for i, (_, text) in enumerate(paired):
                btn = self.option_buttons[i]
                btn.setText(text)
                btn.setVisible(True)
                if str(text).strip().lower() == correct_text:
                    self.correct_option_index = i
        elif qtype == 'true_false':
            self.true_btn.setVisible(True)
            self.false_btn.setVisible(True)
        elif qtype == 'numeric':
            self.numeric_input.setVisible(True)
            self.numeric_submit.setVisible(True)
            self.numeric_input.setFocus()
        self.progress_bar.setValue(self.current_index)

    def handle_multiple_choice(self, idx):
        if not self.questions or self.current_index >= self.total_questions:
            return
        q = self.questions[self.current_index]
        correct_text = str(q.get('correct_answer','')).strip()
        explanation = q.get('explanation','')
        verse = q.get('verse_reference','')
        if idx == self.correct_option_index:
            self.score += 1
            title = 'Correct!'
            body = f"{explanation}\n\nReference: {verse}"
            play_correct_sound()
        else:
            title = 'Incorrect'
            body = f"The correct answer is: {correct_text}\n\n{explanation}\n\nReference: {verse}"
            play_wrong_sound()
        self.score_label.setText(f"Score: {self.score}")
        QMessageBox.information(self, title, body)
        self.current_index += 1
        self.progress_bar.setValue(self.current_index)
        self.load_question()

    def handle_true_false(self, choice):
        if not self.questions or self.current_index >= self.total_questions:
            return
        q = self.questions[self.current_index]
        correct = str(q.get('correct_answer','')).strip().lower()
        explanation = q.get('explanation','')
        verse = q.get('verse_reference','')
        if choice.strip().lower() == correct:
            self.score += 1
            title = 'Correct!'
            body = f"{explanation}\n\nReference: {verse}"
            play_correct_sound()
        else:
            title = 'Incorrect'
            body = f"The correct answer is: {q.get('correct_answer')}\n\n{explanation}\n\nReference: {verse}"
            play_wrong_sound()
        self.score_label.setText(f"Score: {self.score}")
        QMessageBox.information(self, title, body)
        self.current_index += 1
        self.progress_bar.setValue(self.current_index)
        self.load_question()

    def handle_numeric_submit(self):
        if not self.questions or self.current_index >= self.total_questions:
            return
        q = self.questions[self.current_index]
        user = str(self.numeric_input.text()).strip()
        correct_raw = q.get('correct_answer','')
        explanation = q.get('explanation','')
        verse = q.get('verse_reference','')
        ok = False
        if user.lower() == str(correct_raw).strip().lower():
            ok = True
        else:
            user_num = word_to_number(user)
            corr_num = word_to_number(str(correct_raw))
            try:
                if user_num is not None and corr_num is not None and user_num == corr_num:
                    ok = True
                else:
                    if int(user) == int(correct_raw):
                        ok = True
            except Exception:
                ok = ok
        if ok:
            self.score += 1
            title = 'Correct!'
            body = f"{explanation}\n\nReference: {verse}"
            play_correct_sound()
        else:
            title = 'Incorrect'
            body = f"The correct answer is: {correct_raw}\n\n{explanation}\n\nReference: {verse}"
            play_wrong_sound()
        self.score_label.setText(f"Score: {self.score}")
        QMessageBox.information(self, title, body)
        self.current_index += 1
        self.progress_bar.setValue(self.current_index)
        self.load_question()

    def skip_question(self):
        if not self.questions:
            return
        self.current_index += 1
        self.progress_bar.setValue(self.current_index)
        self.load_question()

    def go_previous(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.progress_bar.setValue(self.current_index)
            self.load_question()

    def restart_quiz(self):
        self.close()
        main_startup()

    def finish_quiz(self):
        correct = self.score
        total = self.total_questions
        percent = int((correct / total) * 100) if total > 0 else 0
        try:
            trivia_db.record_used_questions([q.get('id') for q in self.questions])
        except Exception as e:
            logging.error(f"Failed to record used questions: {e}")
        ad_dialog = AdDialog(self)
        ad_dialog.exec_()
        msg = QMessageBox(self)
        msg.setWindowTitle("Quiz Complete")
        msg.setText(f"You answered {correct} out of {total} correctly.\nScore: {percent}%")
        msg.setStandardButtons(QMessageBox.Retry | QMessageBox.Close)
        ret = msg.exec_()
        if ret == QMessageBox.Retry:
            self.restart_quiz()
        else:
            self.close()

def main_startup():
    """Start the quiz application."""
    app = QApplication.instance() or QApplication(sys.argv)
    dlg = StartupDialog()
    if dlg.exec_() == QDialog.Accepted:
        diff = dlg.chosen_difficulty
        limit = dlg.chosen_limit
        try:
            questions = trivia_db.get_random_quiz(limit=limit, difficulty=diff, exclude_used=True)
        except Exception as e:
            logging.error(f"Failed to fetch questions: {e}")
            QMessageBox.critical(None, "Database Error", f"Failed to fetch questions from DB:\n{e}")
            return
        if not questions:
            QMessageBox.information(None, "No Questions", "No questions available for this selection.")
            return
        win = TriviaWindow(questions)
        win.show()
        return win
    return None

if __name__ == '__main__':
    app, splash = show_splash_screen()

    def launch_startup():
        splash.close()
        win = main_startup()
        if win:
            win.show()

    QTimer.singleShot(2500, launch_startup)
    sys.exit(app.exec_())
