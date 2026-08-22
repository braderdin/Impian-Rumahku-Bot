/**
 * 🛍️ LUBUK BARANG MURAH PADU - 24/7 INTERACTIVE TELEGRAM CATALOG BOT (DUAL-PLATFORM ENGINE)
 * Platform: Cloudflare Workers (Edge Serverless)
 * Backend: Supabase PostgreSQL REST API (Lazada: affiliate_links | Shopee: shopee_affiliate_links)
 * UI/UX:
 * 1. Dual-Table Hybrid Search (Merges & displays Shopee + Lazada products seamlessly)
 * 2. Platform Badges [🟠 Shopee | 🔵 Lazada] in list view for crystal-clear clarity
 * 3. 5x2 Number Button Grid (1️⃣ - 🔟) - 100% Responsive on Mobile & Desktop
 * 4. Deep Brand & E-Commerce Tag Sanitizer (Removes redundant names & seller brackets)
 * 5. Smart Stateless Pagination with Combined Exact Record Count
 * 6. One-Click Viral Share & Category Exploration Shortcuts
 */

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const tgToken = env.TELEGRAM_CATALOG_BOT_TOKEN || env.TELEGRAM_BOT_TOKEN;

    // 1. Endpoint Setup Webhook Telegram melalui Pelayar
    if (url.pathname === "/set-webhook") {
      const webhookUrl = `${url.origin}/webhook`;
      const tgRes = await fetch(
        `https://api.telegram.org/bot${tgToken}/setWebhook?url=${encodeURIComponent(webhookUrl)}&drop_pending_updates=true`
      );
      const data = await tgRes.json();
      return new Response(JSON.stringify({ status: "Webhook Configured", result: data, target: webhookUrl }, null, 2), {
        headers: { "Content-Type": "application/json" }
      });
    }

    // 2. Terima Mesej / Klik Butang Webhook daripada Telegram
    if (request.method === "POST" && (url.pathname === "/webhook" || url.pathname === "/")) {
      try {
        const update = await request.json();
        ctx.waitUntil(handleTelegramUpdate(update, env));
        return new Response("OK", { status: 200 });
      } catch (err) {
        return new Response(`Error: ${err.message}`, { status: 500 });
      }
    }

    return new Response("🤖 Lubuk Barang Murah Padu (Shopee + Lazada) Engine is Running 24/7 on Cloudflare Workers!", {
      headers: { "Content-Type": "text/plain; charset=utf-8" }
    });
  }
};

/**
 * Helper Membaca Kunci Supabase & Telegram secara Dinamik
 */
function getKeys(env) {
  return {
    tgToken: env.TELEGRAM_CATALOG_BOT_TOKEN || env.TELEGRAM_BOT_TOKEN || "",
    supabaseUrl: (env.SUPABASE_URL || env.NEXT_PUBLIC_SUPABASE_URL || "").replace(/\/$/, ""),
    supabaseKey: env.SUPABASE_SERVICE_ROLE_KEY || env.SUPABASE_KEY || env.SUPABASE_ANON_KEY || ""
  };
}

/**
 * Normalizer: Menyeragamkan Objek Lazada & Shopee kepada 1 Format Standard
 */
function normalizeProduct(rawItem, platformHint = "Lazada") {
  if (!rawItem) return null;

  // Jika produk dari jadual Shopee
  if (rawItem.shopee_product_id) {
    return {
      product_id: String(rawItem.shopee_product_id).trim(),
      title: rawItem.shopee_product_name || "Produk Shopee",
      price: parseFloat(rawItem.shopee_price) || 0.0,
      category: rawItem.shopee_category || "📦 Tawaran Gajet & Gaya Hidup",
      image_url: rawItem.shopee_picture_url || "",
      affiliate_link: rawItem.shopee_affiliate_link || "",
      brand: rawItem.shopee_brand || "Shopee Official",
      platform: "Shopee"
    };
  }

  // Jika produk dari jadual Lazada
  return {
    product_id: String(rawItem.product_id || rawItem.id || "").trim(),
    title: rawItem.title || rawItem.product_name || "Produk Lazada",
    price: parseFloat(rawItem.price || rawItem.discounted_price || rawItem.sale_price) || 0.0,
    category: rawItem.category || "📦 Tawaran Gajet & Gaya Hidup",
    image_url: rawItem.image_url || rawItem.picture_url || "",
    affiliate_link: rawItem.affiliate_link || rawItem.promo_short_link || "",
    brand: rawItem.brand || "Lazada",
    platform: "Lazada"
  };
}

/**
 * Pengendali Utama Update Telegram
 */
async function handleTelegramUpdate(update, env) {
  // A. KENDALIKAN KLIK BUTANG (CALLBACK QUERY)
  if (update.callback_query) {
    const query = update.callback_query;
    const chatId = query.message.chat.id;
    const messageId = query.message.message_id;
    const data = query.data;

    await callTelegram(env, "answerCallbackQuery", { callback_query_id: query.id });

    if (data === "menu:main") {
      await sendMainMenu(chatId, env, messageId);
    } else if (data === "menu:categories") {
      await sendCategoriesMenu(chatId, env, messageId);
    } else if (data === "menu:hot_deals") {
      await fetchAndShowProductList(chatId, env, "hot", "", 1, messageId);
    } else if (data === "menu:random") {
      await fetchAndShowProductList(chatId, env, "random", "", 1, messageId);
    } else if (data === "menu:help") {
      await sendHelpMessage(chatId, env, messageId);
    } else if (data.startsWith("cat:")) {
      const categoryKey = data.replace("cat:", "");
      await fetchAndShowProductList(chatId, env, "category", categoryKey, 1, messageId);
    } else if (data.startsWith("pnav:")) {
      // Format: pnav:<mode>:<page>:<param>
      const parts = data.split(":");
      const navMode = parts[1] || "search";
      const targetPage = parseInt(parts[2]) || 1;
      const navParam = parts.slice(3).join(":") || "";
      await fetchAndShowProductList(chatId, env, navMode, navParam, targetPage, messageId);
    } else if (data.startsWith("p:")) {
      // Paparkan Kad Perincian Tunggal Produk
      const productId = data.replace("p:", "");
      await showSingleProductDetail(chatId, productId, env);
    }
    return;
  }

  // B. KENDALIKAN MESEJ TEKS DARI PELAWAT
  if (update.message && update.message.text) {
    const chatId = update.message.chat.id;
    const text = update.message.text.trim();
    const userFirstName = update.message.from?.first_name || "Sahabat";

    if (text === "/start" || text.toLowerCase() === "menu") {
      await sendWelcomeAndMenu(chatId, userFirstName, env);
    } else if (text === "/kategori") {
      await sendCategoriesMenu(chatId, env);
    } else if (text === "/bantuan" || text === "/help") {
      await sendHelpMessage(chatId, env);
    } else {
      const querySearch = text.replace("/cari", "").trim();
      await fetchAndShowProductList(chatId, env, "search", querySearch, 1);
    }
  }
}

/* =============================================================================
 * 🎨 FUNGSI MENU UTAMA & PANDUAN (100% HTML FORMATTED)
 * ============================================================================= */

async function sendWelcomeAndMenu(chatId, name, env) {
  const caption = 
    `👋 <b>Hai, ${escapeHtml(name)}!</b>\n` +
    `Selamat Datang ke <b>Lubuk Barang Murah Padu</b> 🔥🛍️\n\n` +
    `Cari pautan rasmi & tawaran diskaun menarik (Shopee & Lazada):\n` +
    `💻 Komputer, Setup & Gajet\n` +
    `🪑 Kerusi Ergonomik & Gaming\n` +
    `🍳 Peralatan Dapur & Rumah\n` +
    `🎣 Hobi & Outdoor / Memancing\n\n` +
    `👇 <b>Sila pilih menu di bawah atau terus taip carian apa-apa barang:</b>`;

  const keyboard = {
    inline_keyboard: [
      [
        { text: "📂 Teroka Kategori", callback_data: "menu:categories" },
        { text: "🔥 Tawaran Hangat", callback_data: "menu:hot_deals" }
      ],
      [
        { text: "🎲 Cadangan Rawak", callback_data: "menu:random" },
        { text: "ℹ️ Bantuan & Info", callback_data: "menu:help" }
      ]
    ]
  };

  await callTelegram(env, "sendMessage", {
    chat_id: chatId,
    text: caption,
    parse_mode: "HTML",
    reply_markup: keyboard
  });
}

async function sendMainMenu(chatId, env, messageId = null) {
  const text = `🛍️ <b>Menu Utama Lubuk Barang Murah Padu (Shopee + Lazada):</b>\n\nPilih mana-mana butang di bawah untuk mula meneroka:`;
  const keyboard = {
    inline_keyboard: [
      [
        { text: "📂 Teroka Kategori", callback_data: "menu:categories" },
        { text: "🔥 Tawaran Hangat", callback_data: "menu:hot_deals" }
      ],
      [
        { text: "🎲 Cadangan Rawak", callback_data: "menu:random" },
        { text: "ℹ️ Bantuan & Info", callback_data: "menu:help" }
      ]
    ]
  };

  await sendOrEditMessage(chatId, text, keyboard, env, messageId);
}

async function sendCategoriesMenu(chatId, env, messageId = null) {
  const text = `📂 <b>Pilih Kategori Produk:</b>\n\nTekan mana-mana kategori untuk melihat senarai barangan terpilih:`;
  const keyboard = {
    inline_keyboard: [
      [
        { text: "🪑 Kerusi Gaming & Ergonomik", callback_data: "cat:chair" },
        { text: "🖥️ Penyejuk & Kipas PC", callback_data: "cat:cooler" }
      ],
      [
        { text: "⚙️ Komponen & Perkakasan PC", callback_data: "cat:hardware" },
        { text: "🎧 Aksesori Gaming & Audio", callback_data: "cat:accessories" }
      ],
      [
        { text: "🍳 Peralatan Dapur & Rumah", callback_data: "cat:kitchen" },
        { text: "🎣 Hobi, Outdoor & Pancing", callback_data: "cat:outdoor" }
      ],
      [
        { text: "🔙 Kembali ke Menu Utama", callback_data: "menu:main" }
      ]
    ]
  };

  await sendOrEditMessage(chatId, text, keyboard, env, messageId);
}

async function sendHelpMessage(chatId, env, messageId = null) {
  const text = 
    `ℹ️ <b>Panduan Carian Pantas Lubuk Barang Murah:</b>\n\n` +
    `1️⃣ <b>Taip Terus:</b> Anda boleh menaip apa-apa nama barang (contoh: <code>kerusi</code>, <code>laptop</code>, <code>keyboard</code>, <code>ugreen</code>, <code>vention</code>).\n` +
    `2️⃣ <b>Senarai Pantas:</b> Bot akan menyaring pangkalan data <b>Shopee & Lazada</b> serentak.\n` +
    `3️⃣ <b>Pilih Nombor:</b> Tekan butang nombor (1️⃣ - 🔟) di bawah senarai untuk melihat gambar HD & pautan pembelian rasmi.\n\n` +
    `Selamat meneroka! ⚡`;

  const keyboard = {
    inline_keyboard: [[{ text: "🔙 Kembali ke Menu Utama", callback_data: "menu:main" }]]
  };

  await sendOrEditMessage(chatId, text, keyboard, env, messageId);
}

/* =============================================================================
 * ⚡ ENJIN SENARAI PRODUK DWI-JADUAL (SHOPEE + LAZADA HYBRID QUERY)
 * ============================================================================= */

async function fetchAndShowProductList(chatId, env, mode, param = "", page = 1, messageId = null) {
  const { supabaseUrl } = getKeys(env);
  const pageSize = 10;
  const offset = (page - 1) * pageSize;

  let lazadaEndpoint = "";
  let shopeeEndpoint = "";
  let headerTitle = "";

  const categoryMap = {
    chair: "🪑 Kerusi Gaming & Ergonomik",
    cooler: "🖥️ Penyejuk & Kipas PC",
    hardware: "⚙️ Komponen & Perkakasan PC",
    accessories: "🎧 Aksesori Gaming & Audio",
    kitchen: "🍳 Peralatan Dapur & Rumah",
    outdoor: "🎣 Hobi & Outdoor / Memancing"
  };

  const halfOffset = Math.floor(offset / 2);

  if (mode === "search") {
    if (!param || param.length < 2) {
      await callTelegram(env, "sendMessage", {
        chat_id: chatId,
        text: "⚠️ Sila taip sekurang-kurangnya 2 huruf untuk membuat carian.",
        parse_mode: "HTML"
      });
      return;
    }
    headerTitle = `🔍 <b>Hasil Carian:</b> "${escapeHtml(param)}"`;
    lazadaEndpoint = `${supabaseUrl}/rest/v1/affiliate_links?title=ilike.*${encodeURIComponent(param)}*&order=id.desc&limit=${pageSize}&offset=${halfOffset}`;
    shopeeEndpoint = `${supabaseUrl}/rest/v1/shopee_affiliate_links?shopee_product_name=ilike.*${encodeURIComponent(param)}*&order=id.desc&limit=${pageSize}&offset=${halfOffset}`;
  } else if (mode === "category") {
    const targetCat = categoryMap[param] || "🪑 Kerusi Gaming & Ergonomik";
    headerTitle = `📂 <b>Kategori:</b> ${escapeHtml(targetCat)}`;
    lazadaEndpoint = `${supabaseUrl}/rest/v1/affiliate_links?category=eq.${encodeURIComponent(targetCat)}&order=id.desc&limit=${pageSize}&offset=${halfOffset}`;
    shopeeEndpoint = `${supabaseUrl}/rest/v1/shopee_affiliate_links?shopee_category=eq.${encodeURIComponent(targetCat)}&order=id.desc&limit=${pageSize}&offset=${halfOffset}`;
  } else if (mode === "hot") {
    headerTitle = `🔥 <b>Tawaran Hangat Terkini:</b>`;
    lazadaEndpoint = `${supabaseUrl}/rest/v1/affiliate_links?price=gt.0&order=id.desc&limit=${pageSize}&offset=${halfOffset}`;
    shopeeEndpoint = `${supabaseUrl}/rest/v1/shopee_affiliate_links?shopee_price=gt.0&order=id.desc&limit=${pageSize}&offset=${halfOffset}`;
  } else if (mode === "random") {
    headerTitle = `🎲 <b>Cadangan Produk Pilihan:</b>`;
    lazadaEndpoint = `${supabaseUrl}/rest/v1/affiliate_links?order=id.desc&limit=${pageSize}&offset=${halfOffset}`;
    shopeeEndpoint = `${supabaseUrl}/rest/v1/shopee_affiliate_links?order=id.desc&limit=${pageSize}&offset=${halfOffset}`;
  }

  // Panggil kedua-dua jadual serentak menggunakan Promise.all untuk kelajuan maksimum
  const [lazadaRes, shopeeRes] = await Promise.all([
    fetchSupabaseWithCount(lazadaEndpoint, env),
    fetchSupabaseWithCount(shopeeEndpoint, env)
  ]);

  const lazadaItems = (lazadaRes.data || []).map(item => normalizeProduct(item, "Lazada")).filter(Boolean);
  const shopeeItems = (shopeeRes.data || []).map(item => normalizeProduct(item, "Shopee")).filter(Boolean);

  // Selang-selikan produk (Shopee & Lazada) secara seimbang
  const combinedProducts = [];
  const maxItems = Math.max(lazadaItems.length, shopeeItems.length);
  for (let i = 0; i < maxItems; i++) {
    if (i < shopeeItems.length) combinedProducts.push(shopeeItems[i]);
    if (i < lazadaItems.length) combinedProducts.push(lazadaItems[i]);
  }

  const products = combinedProducts.slice(0, pageSize);
  const totalCount = (lazadaRes.totalCount || 0) + (shopeeRes.totalCount || 0);

  if (!products || products.length === 0) {
    const emptyKeyboard = {
      inline_keyboard: [
        [{ text: "📂 Pilih Kategori Lain", callback_data: "menu:categories" }],
        [{ text: "🏠 Menu Utama", callback_data: "menu:main" }]
      ]
    };
    await sendOrEditMessage(chatId, `${headerTitle}\n\n😔 <b>Maaf, tiada rekod barangan dijumpai di Shopee atau Lazada.</b> Sila cuba carian kata kunci lain.`, emptyKeyboard, env, messageId);
    return;
  }

  const totalPages = Math.ceil(totalCount / pageSize) || 1;
  const numEmojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"];

  // 1. Bina Teks Senarai Barangan Lengkap (Berserta Lencana Platform Shopee/Lazada)
  let productListText = "";
  for (let i = 0; i < products.length; i++) {
    const item = products[i];
    const itemNum = numEmojis[i] || `${i + 1}️⃣`;
    const priceDisplay = item.price && item.price > 0 ? `RM ${Number(item.price).toFixed(2)}` : `Tawaran`;
    const platformBadge = item.platform === "Shopee" ? "🟠 Shopee" : "🔵 Lazada";
    const cleanTitle = sanitizeFullCatalogTitle(item.title, 70);

    productListText += `${itemNum} <b>[${platformBadge} | ${priceDisplay}]</b> ${escapeHtml(cleanTitle)}\n\n`;
  }

  // 2. Bina Grid Butang Nombor Responsif (Baris 1: 1-5 | Baris 2: 6-10)
  const inlineKeyboardButtons = [];
  const row1 = [];
  const row2 = [];

  for (let i = 0; i < products.length; i++) {
    const item = products[i];
    const btnEmoji = numEmojis[i] || `${i + 1}`;
    const btnObj = { text: btnEmoji, callback_data: `p:${item.product_id}` };

    if (i < 5) {
      row1.push(btnObj);
    } else {
      row2.push(btnObj);
    }
  }

  if (row1.length > 0) inlineKeyboardButtons.push(row1);
  if (row2.length > 0) inlineKeyboardButtons.push(row2);

  // 3. Bina Baris Navigasi Paginasi: [ ◀️ Sebelum ] [ 📄 1/57 ] [ Seterusnya ▶️ ]
  const paginationRow = [];
  const safeParam = String(param).substring(0, 25);

  if (page > 1) {
    paginationRow.push({
      text: "◀️ Sebelum",
      callback_data: `pnav:${mode}:${page - 1}:${safeParam}`
    });
  }

  paginationRow.push({
    text: `📄 ${page}/${totalPages}`,
    callback_data: `pnav:${mode}:${page}:${safeParam}`
  });

  if (page < totalPages) {
    paginationRow.push({
      text: "Seterusnya ▶️",
      callback_data: `pnav:${mode}:${page + 1}:${safeParam}`
    });
  }

  inlineKeyboardButtons.push(paginationRow);

  // 4. Butang Menu Pantas
  inlineKeyboardButtons.push([
    { text: "📂 Kategori Lain", callback_data: "menu:categories" },
    { text: "🏠 Menu Utama", callback_data: "menu:main" }
  ]);

  const fullMessage = 
    `${headerTitle}\n` +
    `<i>Menunjukkan ${products.length} daripada ${totalCount} barangan (Halaman ${page}/${totalPages}):</i>\n\n` +
    `${productListText}` +
    `👇 <b>Tekan nombor pilihan di bawah untuk melihat gambar HD & pautan promosi:</b>`;

  await sendOrEditMessage(chatId, fullMessage, { inline_keyboard: inlineKeyboardButtons }, env, messageId);
}

/* =============================================================================
 * 🖼️ PAPARAN KAD PRODUK TUNGGAL (SEMAK KEDUA-DUA JADUAL AUTOMATIK)
 * ============================================================================= */

async function showSingleProductDetail(chatId, productId, env) {
  const { supabaseUrl } = getKeys(env);
  const cleanId = encodeURIComponent(productId.trim());

  const lazadaEndpoint = `${supabaseUrl}/rest/v1/affiliate_links?product_id=eq.${cleanId}&limit=1`;
  const shopeeEndpoint = `${supabaseUrl}/rest/v1/shopee_affiliate_links?shopee_product_id=eq.${cleanId}&limit=1`;
  
  const [lazadaRes, shopeeRes] = await Promise.all([
    fetchSupabase(lazadaEndpoint, env),
    fetchSupabase(shopeeEndpoint, env)
  ]);

  let item = null;
  if (shopeeRes && shopeeRes.length > 0) {
    item = normalizeProduct(shopeeRes[0], "Shopee");
  } else if (lazadaRes && lazadaRes.length > 0) {
    item = normalizeProduct(lazadaRes[0], "Lazada");
  }

  if (!item) {
    await callTelegram(env, "sendMessage", {
      chat_id: chatId,
      text: "⚠️ Maklumat barangan ini tidak dijumpai atau telah dikemas kini.",
      parse_mode: "HTML"
    });
    return;
  }

  const priceFormatted = item.price && item.price > 0 ? `RM ${Number(item.price).toFixed(2)}` : `Sila semak di pautan rasmi`;
  const cleanDetailTitle = cleanProductDetailTitle(item.title, 85);
  const platformLabel = item.platform === "Shopee" ? "🟠 Shopee Mall / Preferred" : "🔵 Lazada LazMall";
  const buyButtonText = item.platform === "Shopee" ? "🛒 Beli di Shopee (Pautan Rasmi)" : "🛒 Beli di Lazada (Pautan Rasmi)";
  
  // Pautan Telegram Viral Share
  const shareText = `Tengok tawaran ${item.platform} ni: ${cleanDetailTitle} (${priceFormatted})`;
  const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(item.affiliate_link)}&text=${encodeURIComponent(shareText)}`;
  const catKey = getCategoryKeyByName(item.category);

  const caption = 
    `📦 <b>${escapeHtml(cleanDetailTitle)}</b>\n\n` +
    `🏷️ <b>Kategori:</b> ${escapeHtml(item.category || "Umum")}\n` +
    `🏬 <b>Platform:</b> ${platformLabel}\n` +
    `💰 <b>Harga Tawaran:</b> ${priceFormatted}\n` +
    `🛡️ <b>Jaminan:</b> 100% Produk Original & Penjual Sah\n` +
    `🚚 <b>Penghantaran:</b> Pantas & Selamat ke Seluruh Malaysia\n\n` +
    `👇 <b>Tekan butang di bawah untuk membeli atau berkongsi:</b>`;

  const keyboard = {
    inline_keyboard: [
      [{ text: buyButtonText, url: item.affiliate_link }],
      [{ text: "📤 Kongsi Racun Ni ke WhatsApp/Telegram", url: shareUrl }],
      [
        { text: "🔍 Teroka Kategori Sama", callback_data: `cat:${catKey}` },
        { text: "🏠 Menu Utama", callback_data: "menu:main" }
      ]
    ]
  };

  // Hantar Gambar Produk
  if (item.image_url && item.image_url.startsWith("http")) {
    const res = await callTelegram(env, "sendPhoto", {
      chat_id: chatId,
      photo: item.image_url,
      caption: caption,
      parse_mode: "HTML",
      reply_markup: keyboard
    });
    if (!res.ok) {
      await callTelegram(env, "sendMessage", {
        chat_id: chatId,
        text: caption,
        parse_mode: "HTML",
        reply_markup: keyboard
      });
    }
  } else {
    await callTelegram(env, "sendMessage", {
      chat_id: chatId,
      text: caption,
      parse_mode: "HTML",
      reply_markup: keyboard
    });
  }
}

/* =============================================================================
 * 🛠️ PEMBANTU SISTEM, API & SANITIZER
 * ============================================================================= */

async function sendOrEditMessage(chatId, text, keyboard, env, messageId = null) {
  if (messageId) {
    const res = await callTelegram(env, "editMessageText", {
      chat_id: chatId,
      message_id: messageId,
      text: text,
      parse_mode: "HTML",
      reply_markup: keyboard
    });
    if (res.ok) return;
  }

  await callTelegram(env, "sendMessage", {
    chat_id: chatId,
    text: text,
    parse_mode: "HTML",
    reply_markup: keyboard
  });
}

async function fetchSupabase(endpoint, env) {
  const { supabaseKey } = getKeys(env);
  try {
    const res = await fetch(endpoint, {
      headers: {
        apikey: supabaseKey,
        Authorization: `Bearer ${supabaseKey}`,
        "Content-Type": "application/json"
      }
    });
    if (!res.ok) return [];
    return await res.json();
  } catch (e) {
    return [];
  }
}

async function fetchSupabaseWithCount(endpoint, env) {
  const { supabaseKey } = getKeys(env);
  try {
    const res = await fetch(endpoint, {
      headers: {
        apikey: supabaseKey,
        Authorization: `Bearer ${supabaseKey}`,
        "Content-Type": "application/json",
        "Prefer": "count=exact"
      }
    });
    if (!res.ok) return { data: [], totalCount: 0 };
    
    const data = await res.json();
    const contentRange = res.headers.get("content-range") || "";
    let totalCount = Array.isArray(data) ? data.length : 0;
    
    if (contentRange.includes("/")) {
      const parts = contentRange.split("/");
      const parsed = parseInt(parts[1]);
      if (!isNaN(parsed)) totalCount = parsed;
    }

    return { data: Array.isArray(data) ? data : [], totalCount };
  } catch (e) {
    return { data: [], totalCount: 0 };
  }
}

async function callTelegram(env, method, payload) {
  const { tgToken } = getKeys(env);
  const url = `https://api.telegram.org/bot${tgToken}/${method}`;
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: e.message };
  }
}

function escapeHtml(text) {
  if (!text) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function sanitizeFullCatalogTitle(title, maxLen = 75) {
  if (!title) return "Barangan Terpilih";
  
  let clean = title
    .replace(/[\[【][^\]】]*[\]】]/gi, " ")
    .replace(/[\(\)\#\|\/\\]/g, " ")
    .replace(/\s+/g, " ")
    .trim();

  const words = clean.split(" ");
  const uniqueWords = [];
  for (let w of words) {
    if (!w) continue;
    if (uniqueWords.length > 0 && uniqueWords[uniqueWords.length - 1].toLowerCase() === w.toLowerCase()) {
      continue;
    }
    uniqueWords.push(w);
  }
  clean = uniqueWords.join(" ");

  if (clean.length <= maxLen) return clean;
  return clean.substring(0, maxLen).trim() + "...";
}

function cleanProductDetailTitle(title, maxLen = 85) {
  if (!title) return "Produk Pilihan";
  
  let clean = title
    .replace(/[\[【][^\]】]*[\]】]/gi, " ")
    .replace(/[\(\)\#\|\/\\]/g, " ")
    .replace(/\s+/g, " ")
    .trim();

  if (clean.length > maxLen) {
    return clean.substring(0, maxLen).trim() + "...";
  }
  return clean;
}

function getCategoryKeyByName(categoryName) {
  if (!categoryName) return "chair";
  const name = categoryName.toLowerCase();
  if (name.includes("kerusi") || name.includes("chair")) return "chair";
  if (name.includes("penyejuk") || name.includes("cooler") || name.includes("kipas")) return "cooler";
  if (name.includes("komponen") || name.includes("hardware") || name.includes("perkakasan")) return "hardware";
  if (name.includes("aksesori") || name.includes("audio") || name.includes("gaming")) return "accessories";
  if (name.includes("dapur") || name.includes("rumah") || name.includes("kitchen")) return "kitchen";
  if (name.includes("hobi") || name.includes("outdoor") || name.includes("pancing")) return "outdoor";
  return "chair";
}