import random
import datetime
import json
import os
from pygame import mixer
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import time

# Ініціалізація звукової системи
mixer.init()

# Звукові файли
sound_questions = {
    "Кіт": "cat.wav",
    "Собака": "dog.wav",
    "Піаніно": "piano.wav"
}

SAVE_FILE = "progress.json"
LEADERBOARD_FILE = "leaderboard.json"


def play_sound(filename):
    """Відтворення звукового файлу"""
    mixer.music.load(filename)
    mixer.music.play()


def math_question(level):
    """Генерує математичне питання залежно від рівня"""
    a = random.randint(1, 10 * level)
    b = random.randint(1, 10 * level)
    op = random.choice(['+', '-', '*', '/'])
    question = f"{a} {op} {b} = ?"
    if op == '+':
        answer = a + b
    elif op == '-':
        answer = a - b
    elif op == '*':
        answer = a * b
    else:  # Ділення
        answer = round(a / b, 2)
    return question, answer


def date_question():
    """Генерує питання про дати"""
    year = random.randint(2000, 2023)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    date = datetime.date(year, month, day)
    question = f"Чи був {day:02d}-{month:02d}-{year} вихідним днем? (Так/Ні)"
    correct_answer = "Так" if date.weekday() >= 5 else "Ні"
    return question, correct_answer


def sound_question():
    """Генерує звукове питання"""
    sound_name, sound_file = random.choice(list(sound_questions.items()))
    return sound_name, sound_file


def save_progress(name, score, total_time):
    """Зберігає прогрес гравця"""
    data = {"name": name, "score": score, "total_time": total_time}
    with open(SAVE_FILE, "w") as f:
        json.dump(data, f)


def load_progress():
    """Завантажує прогрес гравця"""
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE, "r") as f:
            data = json.load(f)
            return data.get("name", ""), data.get("score", 0), data.get("total_time", 0)
    return "", 0, 0


def save_leaderboard(name, score, time_taken):
    """Зберігає результат у турнірну таблицю"""
    leaderboard = []
    if os.path.exists(LEADERBOARD_FILE):
        with open(LEADERBOARD_FILE, "r") as f:
            leaderboard = json.load(f)
    leaderboard.append({"name": name, "score": score, "time_taken": time_taken})
    leaderboard.sort(key=lambda x: (-x["score"], x["time_taken"]))
    with open(LEADERBOARD_FILE, "w") as f:
        json.dump(leaderboard, f)


def load_leaderboard():
    """Завантажує турнірну таблицю"""
    if os.path.exists(LEADERBOARD_FILE):
        with open(LEADERBOARD_FILE, "r") as f:
            return json.load(f)
    return []


class ModernQuizGame:
    def __init__(self, root):
        self.root = root
        self.root.title("Гра: Вікторина")
        self.root.geometry("600x700")
        self.root.configure(bg="#f7f7f7")

        # Змінні
        self.name, self.score, self.total_time = load_progress()
        self.level = 1
        self.start_time = None

        self.create_main_menu()

    def create_main_menu(self):
        """Створення головного меню гри"""
        # Верхній блок (заголовок, ім'я, рахунок)
        self.header_frame = tk.Frame(self.root, bg="#4682b4", pady=20)
        self.header_frame.pack(fill="x")

        self.label_title = tk.Label(
            self.header_frame, text="Вікторина", font=("Helvetica", 28, "bold"),
            bg="#4682b4", fg="white"
        )
        self.label_title.pack()

        self.label_score = tk.Label(
            self.header_frame, text=f"Рахунок: {self.score}", font=("Arial", 16),
            bg="#4682b4", fg="white"
        )
        self.label_score.pack(pady=5)

        self.label_name = tk.Label(
            self.header_frame, text=f"Гравець: {self.name}", font=("Arial", 14),
            bg="#4682b4", fg="white"
        )
        self.label_name.pack()

        # Центральний блок (кнопки)
        self.center_frame = tk.Frame(self.root, bg="#f7f7f7")
        self.center_frame.pack(expand=True)

        style = ttk.Style()
        style.configure("TButton", font=("Arial", 14), padding=10, relief="flat")

        self.btn_math = ttk.Button(self.center_frame, text="Математика", command=self.start_math)
        self.btn_date = ttk.Button(self.center_frame, text="Дати", command=self.start_date)
        self.btn_sound = ttk.Button(self.center_frame, text="Звуки", command=self.start_sound)
        self.btn_leaderboard = ttk.Button(self.center_frame, text="Турнірна таблиця", command=self.show_leaderboard)
        self.btn_save = ttk.Button(self.center_frame, text="Зберегти прогрес", command=self.save_game)
        self.btn_change_name = ttk.Button(self.center_frame, text="Змінити ім'я", command=self.change_name)
        self.btn_exit = ttk.Button(self.center_frame, text="Вихід", command=self.exit_game)

        self.btn_math.grid(row=0, column=0, padx=15, pady=15, ipadx=20, ipady=10)
        self.btn_date.grid(row=0, column=1, padx=15, pady=15, ipadx=20, ipady=10)
        self.btn_sound.grid(row=1, column=0, padx=15, pady=15, ipadx=20, ipady=10)
        self.btn_leaderboard.grid(row=1, column=1, padx=15, pady=15, ipadx=20, ipady=10)
        self.btn_save.grid(row=2, column=0, padx=15, pady=15, ipadx=20, ipady=10)
        self.btn_change_name.grid(row=2, column=1, padx=15, pady=15, ipadx=20, ipady=10)
        self.btn_exit.grid(row=3, column=0, columnspan=2, padx=15, pady=15, ipadx=20, ipady=10)

    def update_score(self):
        """Оновлення рахунку"""
        self.label_score.config(text=f"Рахунок: {self.score}")

    def start_math(self):
        """Логіка для запуску математичного питання"""
        question, answer = math_question(self.level)
        self.ask_question("Математика", question, answer, 10)

    def start_date(self):
        """Логіка для запуску питання про дати"""
        question, answer = date_question()
        self.ask_question("Дати", question, answer, 15)

    def start_sound(self):
        """Логіка для запуску питання про звуки"""
        correct_answer, sound_file = sound_question()
        options = list(sound_questions.keys())
        random.shuffle(options)
        play_sound(sound_file)

        popup = tk.Toplevel(self.root)
        popup.title("Звуки")
        tk.Label(popup, text="Прослухайте звук і виберіть правильну відповідь:", font=("Arial", 12)).pack(pady=10)
        var = tk.StringVar()
        for i, option in enumerate(options, 1):
            ttk.Radiobutton(popup, text=option, variable=var, value=option).pack(anchor="w")

        def check_answer():
            time_taken = round(time.time() - self.start_time)
            self.total_time += time_taken
            if var.get() == correct_answer:
                messagebox.showinfo("Результат", f"Правильно! +20 балів\nЧас: {time_taken} сек.")
                self.score += 20
                self.level += 1
            else:
                messagebox.showinfo("Результат", f"Неправильно. Це був: {correct_answer}")
            popup.destroy()
            self.update_score()

        self.start_time = time.time()
        ttk.Button(popup, text="Відповісти", command=check_answer).pack(pady=10)

    def ask_question(self, title, question, correct_answer, points):
        """Універсальна функція для показу текстових питань"""
        popup = tk.Toplevel(self.root)
        popup.title(title)
        tk.Label(popup, text=f"Питання: {question}", font=("Arial", 12)).pack(pady=10)
        entry = ttk.Entry(popup, font=("Arial", 12))
        entry.pack(pady=10)

        def check_answer():
            time_taken = round(time.time() - self.start_time)
            self.total_time += time_taken
            user_answer = entry.get().strip()
            if user_answer.lower() == str(correct_answer).lower():
                messagebox.showinfo("Результат", f"Правильно! +{points} балів\nЧас: {time_taken} сек.")
                self.score += points
                self.level += 1
            else:
                messagebox.showinfo("Результат", f"Неправильно. Правильна відповідь: {correct_answer}")
            popup.destroy()
            self.update_score()

        self.start_time = time.time()
        ttk.Button(popup, text="Відповісти", command=check_answer).pack(pady=10)

    def show_leaderboard(self):
        """Відображення турнірної таблиці"""
        leaderboard = load_leaderboard()
        popup = tk.Toplevel(self.root)
        popup.title("Турнірна таблиця")
        tk.Label(popup, text="Турнірна таблиця", font=("Arial", 16, "bold")).pack(pady=10)
        for entry in leaderboard[:10]:
            tk.Label(popup, text=f"{entry['name']}: {entry['score']} балів, {entry['time_taken']} сек.", font=("Arial", 12)).pack()

    def save_game(self):
        """Збереження прогресу"""
        save_progress(self.name, self.score, self.total_time)
        messagebox.showinfo("Збереження", "Прогрес збережено!")

    def change_name(self):
        """Change the player's name"""
        new_name = simpledialog.askstring("Зміна імені", "Введіть нове ім'я:")
        if new_name:
            self.name = new_name
            self.score = 0
            self.total_time = 0
            self.update_score()
            self.label_name.config(text=f"Гравець: {self.name}")
            messagebox.showinfo("Ім'я змінено", f"Ім'я оновлено на {self.name}. Прогрес скинуто.")

    def exit_game(self):
        """Збереження прогресу перед виходом"""
        save_leaderboard(self.name, self.score, self.total_time)
        self.root.quit()


if __name__ == "__main__":
    root = tk.Tk()
    app = ModernQuizGame(root)
    root.mainloop()