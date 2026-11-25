# Deploy guide (Teluglish) - Render

## Important
- Render Blueprint file `render.yaml` is included.
- This configuration uses a persistent disk at `/var/data` so SQLite orders survive redeploys. Render persistent disks are paid; the service plan is set to `starter`.
- Vendor SMS uses Twilio. SMS is sent from the configured Twilio sender to `VENDOR_SMS_NUMBER`; customer phone is only included in the order text.
- Add your actual Twilio credentials and UAE/vendor number in Render environment settings. Never commit credentials.
- Product is alcohol: only operate where legally licensed, with proper age verification and local delivery compliance. Website checkbox alone is not legal age verification.

## Deploy steps
1. Extract this ZIP.
2. Create a private GitHub repository and upload the contents of the `order_website` folder (including `render.yaml`).
3. Sign in to Render and choose **New + -> Blueprint**.
4. Connect the GitHub repository and deploy the Blueprint. Render reads `render.yaml`.
5. In the Render service's Environment settings, enter:
   - `TWILIO_ACCOUNT_SID`
   - `TWILIO_AUTH_TOKEN`
   - `TWILIO_FROM_NUMBER` (Twilio-provided sender number, international format)
   - `VENDOR_SMS_NUMBER` (vendor phone in international format)
6. Save changes and redeploy if prompted.
7. Open the generated `https://...onrender.com` URL and test an order with a small/approved test flow.

## Local run
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000


## Admin dashboard
- Customer checkout submits the order and shows a success page; it does not open WhatsApp.
- Open `/admin/login` on your deployed site. Admin login uses a password only (no username).
- Set `ADMIN_PASSWORD` in Render Environment before using the admin page. Use a long unique password.
- `/admin/orders` lists submitted orders. Tick “Order fulfilled” to mark an order complete.
- `/admin/revenue` shows the sum of fulfilled orders as the revenue/total sold figure.
- Keep `SECRET_KEY` private and use HTTPS.
