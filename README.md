# Styled by Ankita & Arshnoor

Have a closet full of clothes but still feel like you have nothing to wear? Styled helps you put outfits together with what you already own. You can start with a favorite piece, dress for the weather, explore Pinterest inspiration, or look for something new to complete a look.

Styled is for anyone and everyone who feels like they are constantly shopping, forgetting about pieces they own, and wearing the same outfits. Styled aims to help you love what you already own and build a wardrobe that you're excited about. Style inspiration, outfit suggestions, and finding new items are just the beginning. Below each of the key features are detailed with some examples.

## Tools

Styled has seven tools: three fetch external data, three read or update the demo wardrobe, and one displays outfits.

| Tool | What it does |
| --- | --- |
| `get_weather` | Gets a city’s current temperature using the tool presented in class, helping Styled adjust outfits for the weather. |
| `search_products` | Uses SearchApi.io to search Google Shopping for US clothing listings, prices, retailers, images, and links. Results usually match styles rather than exact items. |
| `search_pinterest_pins` | Uses Google Images to find public Pinterest outfit inspiration, returning images and pin links. |
| `search_closet` | Filters the wardrobe by category, color, season, tag, or name, returning item IDs and images. |
| `get_closet_stats` | Summarizes the wardrobe to help spot what you have and what may be missing. |
| `add_closet_item` | Saves an item’s name, category, seasons, and tags. Photos can be added later through **My closet**. |
| `present_outfits` | Turns the model’s selected closet item IDs into visual outfit cards with item photos. |

## How to use it

### Start with a question

![Overall](/images/overall.png)

Type in the chat or choose an example button to fill in a question, then edit it and press **Send**. Include an occasion, color, city, or budget if it matters. Keep refining with follow-ups like “Make it more relaxed,” “Use flat shoes,” or “Give me another option with the same shirt.”

### Pick something from your closet

Open **My closet** in the top-right corner to browse clothing, shoes, and accessories in a scrollable sidebar. This version uses a shared demo wardrobe rather than a personal closet for each visitor.

<img src = "images/my-closet.png" alt = "Closet" width = "40%" height = "50%">

Choose **Style this item** on any piece, including shoes or accessories. The sidebar closes and fills the text bar with a prompt:

> Help me style this item: White cotton button-down shirt.

![Help-Me-Style](/images/help-me-style.png)

Press **Send** to build a look around it. Each outfit gets a short description and its own visual arrangement showing only the selected pieces: top, bottoms, then shoes, with a dress replacing the top and bottoms when appropriate. A white-shirt outfit might include:

- White cotton button-down shirt
- High-rise straight-leg jeans
- White leather sneakers

![Outfit-Suggestions](/images/outfit-suggestions.png)

### Wear more of what you own

Try **One piece, three ways** for different combinations built around a favorite item. Styled uses wardrobe descriptions to plan each look and displays the selected pieces. Tell it when a pairing isn’t your style.

Before shopping, try **Do I need another one?**:

> I’m thinking of buying another black blazer. Check whether I already own something similar before I shop.

Styled compares the item’s category, color, and description with your closet and points out possible overlap. The decision is yours.

![Another-One](/images/another-one.png)

### Add an item or a photo

Choose **Add a new item** and answer the stylist’s questions, or provide the details up front:

> Add a burgundy cardigan to my closet. It’s a top for fall and winter, with work and layering tags.

![New-Item](/images/new-item.png)

Reopen **My closet** to find the item. Select **Add your photo** on its card to save a garment photo for future outfit displays. Images labeled **AI reference image** are generated examples, not photos of the actual clothes.

![New-Item-Closet](/images/new-item-closet.png)

Use **Attach a photo** below the chat to share inspiration and find similar products:

> Find products online similar to the jacket in my attached photo, under 100 USD per item.

You can preview the photo before sending. Both photo controls accept JPEG, PNG, and WebP files up to 5 MB. Clear photos of a single garment work best; searches find similar styles without guaranteeing an exact brand or item.

![Attach-Photo](/images/attach-photo.png)

![Attach-Photo-Results-1](/images/attach-photo-results-1.png)

![Attach-Photo-Results-2](/images/attach-photo-results-2.png)

### A few questions to try

| Ask this | What to expect |
| --- | --- |
| “Put together a work outfit using items from my closet.” | Outfit ideas with the selected pieces pictured together. |
| “Give me three ways to style my black ankle boots.” | Different looks built around the same boots. |
| “What should I wear from my closet for the current weather in New York?” | Outfits suited to the city’s current weather. |
| “Find brown jackets under 100 USD per item.” | Product cards with images, prices, retailers, and **View item** links. |
| “Find Pinterest inspiration for styling black boots for fall.” | Inspiration images with **View pin** links. |
| “Help me dress for a cartoon-character-themed party. Check my closet first, then find anything I’m missing online.” | A character-inspired look using owned pieces, plus shopping suggestions if needed. |
| “What colors and types of clothing do I have most of?” | A wardrobe summary. |

Shopping budgets are in USD per item. Check listings for current prices, sizes, availability, shipping, and tax; some links open Google Shopping before the retailer.

Pinterest searches use public pins, so no account connection is needed. Upload an image you like or describe it to help Styled work from that look.

### See how a suggestion was made

![Tool-Calls](/images/tool-calls.png)

Expand a **Tool call** row to see its name, arguments, and result—whether Styled checked your closet, looked up weather, searched products or pins, or selected an outfit. These traces are part of the project demonstration; you can use the app normally without knowing tool names or reading raw output.

### Your conversation

Follow-ups stay in the same conversation while the tab is open. **New chat** or a page refresh starts fresh. Recent text turns accompany your next message as a fallback if the server instance changes; earlier uploaded photos are not included.

The demo wardrobe is shared. New items and closet photos are saved on the running server instance and may reset when the app restarts or moves to another instance.

### Tool details and memory

For outfit planning, the model uses `search_closet` to find pieces, chooses combinations, and calls `present_outfits` to display them. For a possible repeat purchase, it can compare closet results with the proposed item. It chooses tools based on the request.

The model chooses tools and explains results; Python functions handle data lookups and rule-based comparisons. The `/chat` response includes `response`, `session_id`, and `tool_calls`, with each call’s `name`, `args`, and `result` available in the interface.

To try conversation memory, ask for a look with flat shoes, then say “Make it suitable for work, but keep my shoe preference.” Use **New chat** before trying another person’s preferences.
