# Echo lead finder: Google Places key (one-time, about 5 minutes)

Echo's **Website and Leads Manager** finds 20 new southern Adelaide businesses every day at 3 PM (or when you send `/findleads` on Telegram). For each one it saves the phone, address, opening hours, rating, whether they have a website, an email if their own website publishes one, 2 photos, and a ready-to-build `brief.md` for Base44. Everything goes in `Echo_leads` in your user folder; `leads.csv` opens in Excel.

## Get the key
1. Go to **console.cloud.google.com** and sign in with your Google account.
2. Create a project (top bar → **New project**), name it "Echo".
3. Open **APIs & Services → Library**, search **Places API (New)** and click **Enable**.
4. Google asks you to set up billing (a card). Echo stays within or close to the free monthly allowance (see below).
5. Open **APIs & Services → Credentials → Create credentials → API key**. Copy the key.
6. Click the key, choose **Restrict key → Places API (New)**, and save. That way it can only be used for this.

## Give it to Echo
Double-click `setup_echo.bat` in your Echo folder. Press Enter to keep your existing settings, and paste the key when it asks for the **Google Places API key**. Then restart Echo with `start_echo`.

## What it costs
Google gives a free allowance each month: 1,000 detailed searches and 1,000 photos. A daily run uses about 7 to 15 searches and 40 photos, so searches stay free. Photos come to about 1,200 a month, which is roughly **US$1–2 a month** above the free allowance at Google's current prices. You can set a budget alert in Google Cloud under **Billing → Budgets**.

## Good to know
- Emails only appear when the business's own website publishes one. Businesses with no website (the best leads) usually have phone numbers only.
- Photos come from Google and are credited in each brief. Before a site goes live, ask the owner for their own photos or permission.
- Echo never contacts businesses. You decide who to approach.
