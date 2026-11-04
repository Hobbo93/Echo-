# Connect Echo to OpusClip (YouTube, Instagram, TikTok)

Once connected, Echo's **Content Creator** can:
- **Make clips:** `/clip https://youtube.com/watch?v=...` or `/clip latest` (the newest video in the `content_input` folder). OpusClip cuts it into short clips with captions. Echo messages you when they're ready, usually in 10 to 30 minutes.
- **Show clips:** `/clips` lists them with a link to watch each one.
- **Post:** `/post 1 youtube instagram` posts clip 1 now. `/post 1 tiktok at 6pm` schedules it (Adelaide time). `/post 1 all` posts to every linked account except X.
- **Check accounts:** `/opus` shows where OpusClip can post.

Making clips uses OpusClip credits, and posting is public. Echo shows you exactly what it will do (video, title, caption, accounts, time) and waits for you to tap **✅ Yes**.

## One-time setup (2 minutes)
1. Log in at **clip.opus.pro**. Your Pro plan includes the API (beta), with 900 API credits a month.
2. Make sure YouTube, Instagram and TikTok are linked in OpusClip (**Social accounts**). They already are: Stringman135, brainyburstclips and viralvideos8967.
3. In the OpusClip dashboard, open **API key** (bottom-left corner) and copy it.
4. On the PC, double-click **`connect_echo.bat`**, say **y** to OpusClip and paste the key.
5. On Telegram, send `/opus`. It should list your accounts.

Never send the API key in a chat. It's stored only on your PC, in `.echo_telegram.json` in your user folder. Everything Echo posts is logged in `Echo_business\opusclip_log.json`.
