// Cloudflare Worker (тегін, 24/7): Telegram webhook-ты қабылдап, бірден "200 OK" қайтарады
// және сұранысты Google Apps Script-ке жібереді. Нәтиже: Telegram қайта-қайта жібермейді (302 қатесі жоқ),
// бот тез және дубльсіз жауап береді.
//
// Орнату: Cloudflare -> Workers & Pages -> Create -> Worker -> Edit code -> осыны қойыңыз -> Deploy.
// Settings -> Variables and Secrets -> Add: SECRET = (webhook құпиясы, Apps Script-тегі SECRET-пен бірдей) -> Deploy.
// Webhook мекенжайлары:
//   Саят · Ассистент:  https://<worker>.workers.dev/<SECRET>/assist
//   Бот Кейс:          https://<worker>.workers.dev/<SECRET>/keis
const TARGET = 'https://script.google.com/macros/s/AKfycbyIP-sAIHtAnQ2PlvS2Irs31ubBodosqpYOckIBwsODYTmksEWH-H-CveX41GiYE1y9/exec';

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method !== 'POST') return new Response('relay ok');
    const parts = url.pathname.split('/').filter(Boolean);
    if (!env.SECRET || parts[0] !== env.SECRET) return new Response('not found', { status: 404 });
    const bot = parts[1] === 'keis' ? '&bot=keis' : '';
    const body = await request.text();
    const target = TARGET + '?k=' + encodeURIComponent(env.SECRET) + bot;
    // Жауапты күтпейміз: Telegram-ға бірден 200 қайтарамыз, Apps Script фонда өңдейді.
    ctx.waitUntil(fetch(target, { method: 'POST', headers: { 'content-type': 'application/json' }, body, redirect: 'follow' }).catch(function () {}));
    return new Response('ok', { status: 200 });
  }
};
