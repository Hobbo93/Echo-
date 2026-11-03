# Connect Echo to your Shopify store

Once connected, the **Shopify Manager** really works on your store (Furventure, `thedogden-2.myshopify.com`). It can:
- **Add products**: "add a waterproof dog jacket, $39.95, 20 in stock". Echo writes the description. Send a photo on Telegram with that as the caption and the photo goes on the listing.
- **Change prices**: "change Dog Bed price to $49", or put something on sale.
- **Set stock**: "set the stock of Dog Bed to 12".
- **Edit listings**: new title, description or tags, or set it to draft, live or archived.
- **Make discount codes**: "make a 15% off code SPRING15 for 2 weeks".
- **Read**: "show my products", "low stock", "latest orders" (or /shop, /orders).

Every change is sent to your phone first. Nothing happens until you tap **✅ Yes** on Telegram (or say yes on the phone line).

## One-time setup (about 5 minutes)
Since January 2026, Shopify apps are made in the **Dev Dashboard**.

1. In your Shopify admin go to **Settings → Apps → Develop apps**, then **Build apps in Dev Dashboard** (or go straight to dev.shopify.com/dashboard). Log in with the same account that owns your store.
2. Click **Create app** and name it `Echo`.
3. Create a **version**. Under **Access → Scopes**, tick these Admin API scopes:
   `read_products, write_products, read_inventory, write_inventory, read_locations, read_orders, read_discounts, write_discounts, read_publications, write_publications`
   Then **Release** the version.
4. Click **Install app** and choose your store (Furventure). Approve the access.
5. Open the app's **Settings** and copy the **Client ID** and **Client secret**.
6. On the PC, double-click **`connect_echo.bat`**. Say **y** to Shopify and paste:
   - Store address: `thedogden-2.myshopify.com`
   - Client ID
   - Client secret

The wizard then tests the connection and shows **🟢 Shopify Manager → Your Shopify store** with your product count. Echo swaps the Client ID and secret for a fresh 24-hour key by itself, so you never have to renew anything.

**If Shopify gives you an Admin API access token** (starts with `shpat_`, from an older custom app), paste that into the "OR an Admin API token" box instead.

**If the test says `shop_not_permitted`,** the app isn't installed on the store, or it was made under a different Shopify login. Install it on Furventure from the Dev Dashboard (step 4).

Your keys are stored only on your PC, in `.echo_telegram.json` in your user folder. Every change Echo makes is logged in `Echo_business\shopify_log.json`.
