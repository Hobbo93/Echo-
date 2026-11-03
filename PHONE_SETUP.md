# Echo phone calls

## What Echo does with its phone number
- **Your employees ring you when they need you:** a trade idea to approve, an Echo update, an urgent customer, follow-ups due, or something broken. Echo explains, and you can just say **"yes"** or **"no"** on the call to approve or skip a trade or update. Details and charts also go to Telegram.
- **You can ring Echo any time:** it tells you what the employees need, then you just talk.
- **It doesn't pester you:** each new issue gets one call, at most 6 calls a day, and none between 9 PM and 8 AM.
- `/callme` on Telegram or **Ring my phone** in Echo HQ rings you straight away.


With this set up you can **ring Echo** from your mobile, and **Echo can ring you** (tap **📱 Ring my phone** in Echo HQ, or send `/callme` to the Echo chat bot on Telegram). You talk normally; Echo answers in an Australian voice. Say "bye" to hang up.

It works while your PC is on and Echo is running.

## What it costs

Echo uses **Twilio** for the phone number. Prices change, so check Twilio's site. Roughly:
- an Australian mobile number: a few dollars a month
- calls: a few cents a minute

Twilio gives you free trial credit to start. On a trial account Twilio plays a short message at the start of each call, and can only call numbers you've verified.

## Steps

1. Sign up at **twilio.com** and verify your own mobile number.
2. Buy a phone number (**Phone Numbers → Buy a number**). Australian numbers need you to submit an address and ID first (Twilio calls this a *regulatory bundle*); it can take a day or two to be approved.
3. On the Twilio Console home page, copy your **Account SID** and **Auth Token**.
4. Double-click `setup_echo.bat`:
   - choose **Y** to install the free tunnel (it lets Twilio reach your PC safely)
   - answer **y** to "Set up phone calls" and paste your Account SID, Auth Token, your Twilio number and your own mobile number. Write numbers like `+61412345678` (with +61, no leading 0).
5. Double-click `start_echo.bat`. An **Echo Phone** window opens and says when the line is ready.

## Good to know

- Only calls from **your** mobile are answered. Anyone else hears "Sorry, this line is private."
- The rest of Echo (approvals, tasks, Echo HQ) is never reachable from the internet. Only the phone part is, and every request is checked to be really from Twilio.
- Echo's answers come from the AI on your PC. If your PC is slow, Echo may say its brain isn't responding. Twilio only waits about 15 seconds for each answer.
- The tunnel address changes every time Echo starts. Echo updates Twilio automatically, so there's nothing to do.
