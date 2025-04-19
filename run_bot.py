import customtkinter as ctk
import subprocess
import sys
import threading
import queue
import time
import re
import io
from datetime import datetime
from pystray import Icon as TrayIcon, MenuItem as item
from PIL import Image, ImageDraw

# ---------- Appearance ----------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# ---------- Globals ----------
log_queue = queue.Queue()
bot_process = None
tray_thread = None  # will hold our pystray thread
bot_name = "Casino Bot Console"

last_line_text = ""
last_line_tag = None
repeat_count = 0

# ---------- Helpers for a circular icon ----------
def make_circle_image(color: str, size=64, radius=64) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    xy = ((size - radius) // 2, (size - radius) // 2,
          (size + radius) // 2, (size + radius) // 2)
    draw.ellipse(xy, fill=color)
    return img

# ---------- Capture stdout/stderr into our queue ----------
class QueueWriter(io.TextIOBase):
    def write(self, text):
        if text.strip():
            log_queue.put((text, "command", True))
    def flush(self):
        pass

sys.stdout = QueueWriter()
sys.stderr = QueueWriter()

# ---------- Log formatting ----------
ANSI_ESCAPE     = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
LOGSTAMP_PREFIX = re.compile(
    r'^[A-Z] \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}\s+[\w\.]+:\s'
)

def format_line(raw, tag=None, is_manual=False):
    if is_manual:
        ts = datetime.now().strftime("[%#m-%#d-%y | %#I:%M%p]").lower() \
               .replace("am","a").replace("pm","p")
        return f"{ts} [{tag.upper()}] {raw}\n", tag

    stripped = ANSI_ESCAPE.sub("", raw).strip()
    if not stripped:
        return "", None
    stripped = LOGSTAMP_PREFIX.sub("", stripped)

    # skip known ASCII banners
    for prefix in ("`888","888 .oo.","888P\"Y88b","888   888","o888o"):
        if stripped.startswith(prefix):
            return "", None

    # replace version line
    m = re.match(r'^.*?(\d+\.\d+\.\d+).*\[[0-9a-f]{6,}\]$', stripped)
    if m:
        version = m.group(1)
        ts = datetime.now().strftime("[ %#m-%#d-%y | %#I:%M%p ]") \
               .lower().replace("am","a").replace("pm","p")
        return f"{ts} Hikari running on version {version}\n", "hikari"

    now = datetime.now()
    date = now.strftime("%-m-%-d-%y") if sys.platform!="win32" \
           else now.strftime("%#m-%#d-%y")
    tp = now.strftime("%-I:%M%p") if sys.platform!="win32" \
         else now.strftime("%#I:%M%p")
    tp = tp.lower().replace("am","a").replace("pm","p")
    ts = f"[ {date} | {tp} ]"

    low = stripped.lower()
    if "error" in low or "traceback" in low:
        tag = "error"
    elif "warn" in low:
        tag = "warn"
    elif "debug" in low:
        tag = "debug"
    elif "info" in low or "started" in low or "ready" in low:
        tag = "info"
    else:
        tag = "default"

    if "hikari" in low:
        tag = "hikari"

    return f"{ts} {stripped}\n", tag

# ---------- Bot control ----------
def start_bot():
    global bot_process
    if bot_process and bot_process.poll() is None:
        log_queue.put(("Bot is already running.", "info", True))
        return

    def runner():
        global bot_process
        try:
            bot_process = subprocess.Popen(
                [sys.executable, "-OO", "-m", "gambling"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1
            )
            set_tray_icon("running")
            for line in bot_process.stdout:
                log_queue.put((line, None, False))
            # exited
            set_tray_icon("stopped")
            log_queue.put(("Bot process ended.", "info", True))
        except Exception as e:
            set_tray_icon("error")
            log_queue.put((f"Failed to start bot: {e}", "error", True))

    threading.Thread(target=runner, daemon=True).start()

def stop_bot():
    global bot_process
    if bot_process and bot_process.poll() is None:
        bot_process.terminate()
        log_queue.put(("Bot terminated by user.", "warn", True))
    else:
        log_queue.put(("Bot is not running.", "info", True))
    set_tray_icon("stopped")

restart_in_progress = False
def restart_bot():
    global restart_in_progress
    if restart_in_progress:
        return
    restart_in_progress = True
    stop_bot()
    time.sleep(1)
    start_bot()
    log_queue.put(("Bot restarted by user.", "info", True))
    restart_in_progress = False

# ---------- Tray‐icon state helper ----------
current_state = None
tray_icon_ref = None

def set_tray_icon(state: str):
    """ Update the tiny circle color on the tray icon. """
    global current_state
    current_state = state
    if tray_icon_ref:
        tray_icon_ref.icon = make_circle_image({
            "running": "green",
            "stopped": "grey",
            "error":   "red"
        }[state])

# ---------- Build the GUI ----------
app = ctk.CTk()
app.geometry("700x460")
app.title(bot_name)

# Log text box
log_output = ctk.CTkTextbox(app, height=320, width=660,
                             corner_radius=6, font=("Cabin",14),
                             wrap="word")
log_output.pack(pady=(20,10), padx=20)

for tag,color in [
    ("timestamp","#888888"),("repeat","#AAAAAA"),("hikari","#D19EFF"),
    ("command","#00FF7F"),("info","#00BFFF"),("warn","#FFD700"),
    ("error","#FF4C4C"),("debug","#A9A9A9"),("default","white")
]:
    log_output.tag_config(tag, foreground=color)

# Buttons
btn_frame = ctk.CTkFrame(app, fg_color="transparent")
btn_frame.pack(pady=5)
ctk.CTkButton(btn_frame, text="Start Bot",   width=100,
              fg_color="#6fe39c", command=start_bot).grid(row=0,column=0,padx=10)
ctk.CTkButton(btn_frame, text="Restart Bot", width=120,
              fg_color="#e6ce65", command=restart_bot).grid(row=0,column=1,padx=10)
ctk.CTkButton(btn_frame, text="Stop Bot",    width=100,
              fg_color="#e34050", command=stop_bot).grid(row=0,column=2,padx=10)

# Checkboxes
min_to_tray = ctk.BooleanVar(value=False)
ctk.CTkCheckBox(app, text="Minimize to Tray on Close",
                variable=min_to_tray).pack(side="left",
                anchor="s", padx=20, pady=10)

always_on_top = ctk.BooleanVar(value=False)
ctk.CTkCheckBox(app, text="Always on Top",
                variable=always_on_top,
                command=lambda: app.attributes("-topmost", always_on_top.get())
).pack(side="left", anchor="s", padx=(0,20), pady=10)

# ---------- Log‐pump ----------
def update_logs():
    global last_line_text, last_line_tag, repeat_count
    try:
        while True:
            raw, tag, is_manual = log_queue.get_nowait()
            text, tag = format_line(raw, tag, is_manual)
            if not text:
                continue

            # detect repeats
            if text.strip() == last_line_text.strip() and tag == last_line_tag:
                repeat_count += 1
                log_output.delete("end-2l","end-1l")
                log_output.insert("end",f"↑ repeated {repeat_count} times\n","repeat")
            else:
                last_line_text, last_line_tag = text, tag
                repeat_count = 0
                if text.startswith("[ ") and " | " in text:
                    i = text.find("]")+1
                    log_output.insert("end", text[:i], "timestamp")
                    log_output.insert("end", text[i:], tag)
                else:
                    log_output.insert("end", text, tag)
            log_output.see("end")
    except queue.Empty:
        pass
    app.after(100, update_logs)

# ---------- Tray‐icon callbacks ----------
def on_tray_show(icon, item=None):
    icon.stop()
    app.after(0, lambda: (app.deiconify(), app.lift(), app.focus_force()))

def on_tray_quit(icon, item=None):
    stop_bot()
    icon.stop()

def make_tray():
    """ Called when we actually close to tray """
    global tray_icon_ref
    img = make_circle_image("grey")
    menu = (item("Show", on_tray_show, default=True),
            item("Quit", on_tray_quit))
    icon = TrayIcon("Casino Bot", img, menu=menu,
                    on_activate=on_tray_show)
    tray_icon_ref = icon
    set_tray_icon(current_state or "stopped")
    icon.run()  # blocks until .stop()

# ---------- Close override ----------
def on_close():
    if min_to_tray.get():
        app.withdraw()
        # spawn one tray thread (will auto‐stop when you restore)
        threading.Thread(target=make_tray, daemon=True).start()
    else:
        stop_bot()
        try: tray_icon_ref.stop()
        except: pass
        app.destroy()

app.protocol("WM_DELETE_WINDOW", on_close)

# ---------- Fire it up ----------
update_logs()
app.mainloop()
