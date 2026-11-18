"""Echo in your Twitch chat. Started by echo_start.py when Twitch is connected; it only talks while you've
switched it on with /twitch bot on (and stops with /twitch bot off).

Viewers type  !echo <question>  or  !ask <question>  or @mention the bot, and Echo answers in one short line.
Echo never promises giveaways, links, prices or actions, never asks for personal details, and ignores
anyone it's already answered in the last 30 seconds. Standard library only (Twitch chat is IRC over TLS).
"""
import re
import socket
import ssl
import time

import echo_business
import echo_log
import echo_twitch

HOST, PORT = "irc.chat.twitch.tv", 6697
COOLDOWN = 30          # seconds per viewer
MAX_PER_MINUTE = 12    # all replies together, well under Twitch's limits
TRIGGER = re.compile(r"^\s*!(echo|ask)\b\s*(.*)$", re.I)

SYSTEM = (
    "You are Echo, the friendly AI assistant in this Twitch streamer's chat. Answer the viewer in ONE short, "
    "friendly line (under 300 characters), plain text, no links, no hashtags. Never promise giveaways, prizes, "
    "money, follows, shout-outs or anything the streamer hasn't said; never ask for personal details; don't "
    "claim to have done anything. Keep it clean and kind. If you don't know, say so briefly. "
    "If someone is rude or asks something unsafe, politely decline."
)


def clean(text):
    text = re.sub(r"https?://\S+", "", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:400]


def answer(viewer, question, title=""):
    prompt = (f"Stream title: {title}\n" if title else "") + f"Viewer {viewer} asks: {question[:300]}"
    try:
        reply = echo_business.ask_ai(prompt, system=SYSTEM, timeout=60)
    except Exception as exc:
        echo_log.error("twitch bot ai", exc)
        return ""
    return clean(reply)


def parse(line):
    """(viewer, text) for a chat message, or None."""
    m = re.match(r"^(?:@\S+ )?:(\w+)!\S+ PRIVMSG #\w+ :(.*)$", line)
    return (m.group(1), m.group(2)) if m else None


def wants_reply(text, bot_login):
    m = TRIGGER.match(text)
    if m:
        return m.group(2).strip()
    if bot_login and re.search(r"@" + re.escape(bot_login) + r"\b", text, re.I):
        return re.sub(r"@" + re.escape(bot_login) + r"\b", "", text, flags=re.I).strip()
    return None


class Limiter:
    def __init__(self):
        self.viewers, self.sent = {}, []

    def ok(self, viewer, now=None):
        now = now or time.time()
        self.sent = [t for t in self.sent if now - t < 60]
        if now - self.viewers.get(viewer.lower(), 0) < COOLDOWN or len(self.sent) >= MAX_PER_MINUTE:
            return False
        self.viewers[viewer.lower()] = now
        self.sent.append(now)
        return True


def run_once(token, login):
    """Connect, chat until the bot is switched off or the connection drops."""
    chan = "#" + echo_twitch.channel()
    raw = socket.create_connection((HOST, PORT), timeout=30)
    sock = ssl.create_default_context().wrap_socket(raw, server_hostname=HOST)
    sock.settimeout(5)

    def say(line):
        sock.sendall((line + "\r\n").encode("utf-8"))

    say("PASS oauth:" + token)
    say("NICK " + login)
    say("JOIN " + chan)
    print(f"Echo is in {chan} chat as {login}. Viewers: !echo <question>", flush=True)
    limiter, buf, title, title_at = Limiter(), "", "", 0.0
    try:
        while echo_twitch.bot_enabled():
            try:
                chunk = sock.recv(4096).decode("utf-8", "replace")
            except socket.timeout:
                continue
            if not chunk:
                return  # disconnected: the outer loop reconnects
            buf += chunk
            *lines, buf = buf.split("\r\n")
            for line in lines:
                if line.startswith("PING"):
                    say("PONG" + line[4:])
                    continue
                if "Login authentication failed" in line or "Improperly formatted auth" in line:
                    raise PermissionError("Twitch sign-in for the chat bot was refused")
                msg = parse(line)
                if not msg or msg[0].lower() == login.lower():
                    continue
                question = wants_reply(msg[1], login)
                if not question or not limiter.ok(msg[0]):
                    continue
                if time.time() - title_at > 600:
                    title_at = time.time()
                    try:
                        live = echo_twitch.stream()
                        title = live.get("title", "") if live else ""
                    except Exception:
                        pass
                reply = answer(msg[0], question, title)
                if reply:
                    say(f"PRIVMSG {chan} :@{msg[0]} {reply}")
    finally:
        try:
            sock.close()
        except OSError:
            pass


def main():
    print("Echo Twitch chat bot ready. It talks only while it's switched on (/twitch bot on).", flush=True)
    wait = 10
    while True:
        try:
            if not echo_twitch.is_configured() or not echo_twitch.bot_enabled():
                time.sleep(15)
                continue
            token, login = echo_twitch.chat_token()
            if not token:
                time.sleep(30)
                continue
            run_once(token, login)
            wait = 10
        except KeyboardInterrupt:
            return
        except Exception as exc:
            echo_log.error("twitch bot", exc)
            print("Twitch chat problem:", str(exc)[:200], f"(trying again in {wait}s)", flush=True)
            time.sleep(wait)
            wait = min(300, wait * 2)


if __name__ == "__main__":
    echo_log.install()
    main()
