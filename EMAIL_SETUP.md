# Connect Echo to your Gmail

With Gmail connected, the **Sales Agent** and **Customer Support** can send real emails from your address:
- `email Joe's Plumbing`: Echo writes an outreach email to that lead from your pipeline, sends it to your phone, and emails it only after you tap **✅ Yes**. The lead is then marked "contacted".
- `email bob@example.com about the website mock-up being ready`: Echo writes the email and asks before sending.

Nothing is ever sent without your Yes. A log of sent emails is kept in `Echo_business\emails_sent.json`.

## One-time setup (about 3 minutes)
Google needs an **app password** for this. It's not your normal password, and you can delete it any time.

1. Turn on **2-Step Verification** for your Google account (myaccount.google.com → Security), if it isn't on already.
2. Go to **myaccount.google.com/apppasswords**, type `Echo` as the name, and click **Create**.
3. Copy the 16-letter password Google shows you.
4. On the PC, double-click **`connect_echo.bat`**, say **y** to Gmail, and enter your Gmail address and that app password.

The wizard tests it and shows **🟢 Sales Agent + Support → Your Gmail**.
