SINGLE PRODUCT ORDER WEBSITE - TELUGISH SETUP

1. ZIP extract cheyyandi.
2. VS Code lo order_website folder open cheyyandi.
3. Terminal lo commands:

   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   python app.py

4. Browser lo http://127.0.0.1:5000 open cheyyandi.

Mee product name, description, price, image ni app.py lo PRODUCTS list lo change cheyyandi.
Product image ni static/RSDW.jpeg ga replace cheyyandi.
Vendor ki automatic SMS pampadaniki Twilio account avasaram. Render Environment lo TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, VENDOR_SMS_NUMBER set cheyyandi. Vendor number country code tho E.164 format lo undali, example +971...

Order total = product price x quantity. Delivery fee ledu; database lo delivery_fee column ledu.
Customer Submit click chesaka order database lo save avuthundi. Twilio settings correct ga unte business sender nunchi vendor mobile ki SMS automatic ga velthundi. Customer phone number sender ga use cheyyadu.

Alcohol product kabatti applicable local laws, licence, legal-age verification, and delivery rules follow cheyyali. Checkout checkbox actual age verification ki substitute kaadu.
